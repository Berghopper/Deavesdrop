import asyncio
import gc
import io
import multiprocessing as mp
import os
import select
import struct
import sys
import threading
import time
from datetime import datetime

import discord
import discord.opus as opus
from discord.opus import DecodeManager, OpusError
from discord.sinks import (AudioData, Filters, MP3Sink, RawData,
                           RecordingException)
from dotenv import dotenv_values

from ffmpeg_util import write_wav_btyes_to_mp3_file

# globals
config = dotenv_values(".env")

MAX_MB_BEFORE_FLUSH = int(config["MAX_MB_BEFORE_FLUSH"])

"""
Reimplements some pycord classes to allow flushing audio data to disk when it gets too big.
"""


class MemoryConciousAudioData(AudioData):
    """
    Adds: keep track of files on disk, so we can merge them later.
    """

    def __init__(self, file):
        super().__init__(file)
        self.files_on_disk = []

    def get_actual_files(self):
        """
        Yields the actual files on disk/non-empty files.
        """
        for fn in self.files_on_disk:
            if os.path.exists(fn) and os.path.getsize(fn) > 0:
                yield fn

    def on_format(self, encoding):
        """super is blocking, while recording, maybe not needed (depends on the sink)"""
        return


# override mp3sink, write is in memory...
class MemoryConsiousMP3Sink(MP3Sink):
    """
    A memory conscious MP3Sink, to be used with MemoryConsiousVoiceClient.
    It flushes audio data to a file when it gets too big.

    Each user has a file until the recording is finished.
    max_size_mb is the max size in memory of all users before flushing to a file.
    keep in mind we might still have more than max_size_mb in memory, so be conservative.

    We have a file per user, and we write to the file as we receive audio data.
    During write method, we check how big the bytesIO has gotten, and if it's too big, we flush to a file.
    """

    def __init__(
        self,
        *,
        filters=None,
        max_before_flush=100,
        max_size_mb=200,
        output_folder="output",
        output_fn=None,
    ):
        super().__init__(filters=filters)
        self.max_mb_before_flush = max_before_flush
        self.max_size_mb = max_size_mb
        self.output_folder = output_folder
        self.write_threads = []
        if output_fn:
            self.output_fn = output_fn
        os.makedirs(output_folder, exist_ok=True)

    def get_total_size(self):
        return sum([audio.file.tell() for audio in self.audio_data.values()])

    def should_flush(self, n=0):
        """
        Checks if we should flush the audio data to a file.
        n is bytessize if we want to check if we will go over the limit.
        """
        # print(f"Total size: {self.get_total_size() / (1024 * 1024)}")
        # print(f"Max size: {self.max_mb_before_flush}")
        return self.get_total_size() + n > (self.max_mb_before_flush * 1024 * 1024)

    def should_wait_for_memory(self, n=0):
        """
        We should await when we have too much memory in threads OR if we have too many threads already running.
        """
        # print(f"Memory in threads: {self.mem_in_threads / (1024 * 1024)}")
        # print(f"Max thread size: {self.max_size_mb}")

        # Max threads allowed is at least 1, but at most cpu_count - 1.
        max_threads_allowed = min(1, mp.cpu_count() - 1)
        return (self.mem_in_threads() + n > (self.max_size_mb * 1024 * 1024)) or len(
            self.write_threads
        ) >= max_threads_allowed

    def mem_in_threads(self):
        # First reomve dead threads
        new_write_threads = []
        for t, size in self.write_threads:
            if t.is_alive():
                new_write_threads.append((t, size))
        self.write_threads = new_write_threads
        return sum([size for t, size in self.write_threads if t.is_alive()])

    def await_free_mem(self):
        """
        Waits for the memory to be freed by the threads.
        Decoder might back up, but we can't do much about that.
        """
        print("Waiting for memory to be freed... too much memory stuck in threads.")
        while self.should_wait_for_memory():
            time.sleep(0.1)
        gc.collect()
        print("Memory freed! Resuming...")

    def flushToFiles(self, force_all=False):
        """
        Swap out all the BytesIO objects for FileIO objects (if they're not already).
        """
        current_size = self.get_total_size()
        # print("Flushing to files...")
        for user_id, audio in self.audio_data.items():
            if not hasattr(audio, "files_on_disk"):
                raise ValueError(
                    f"Wrong AudioData instance for {self.__class__.__name__}, needs to be MemoryConciousAudioData"
                )

            fn = f"{self.output_folder}/{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.mp3"
            audio_size = audio.file.tell()
            # Check if empty, if it is, we don't need to write to a file.
            if audio_size == 0:
                continue
            current_size_too_big = current_size > (
                (self.max_mb_before_flush * 1024 * 1024) * 2
            )
            # If not empty, check if at least 10mb, if not, don't write to a file yet. (unless force_all or current_size is 2x over the limit)
            if (
                audio_size < (10 * 1024 * 1024)
                and not force_all
                and not current_size_too_big
            ):
                continue
            audio.files_on_disk.append(fn)
            if self.should_wait_for_memory(audio_size):
                self.await_free_mem()
            t = threading.Thread(
                target=write_wav_btyes_to_mp3_file,
                args=(
                    io.BytesIO(audio.file.getvalue()),
                    fn,
                ),
            )
            t.start()
            # keep track of threads, so we can wait for them later.
            self.write_threads.append((t, audio_size))
            # Possibly await here too, might be a big one.
            if self.should_wait_for_memory():
                self.await_free_mem()
            # now we can wipe the current BytesIO
            audio.file.seek(0)
            audio.file.truncate(0)

    def format_audio(self, audio):
        """
        Has no use besides being called by cleanup in super.
        We don't need to.
        """
        return

    @Filters.container
    def write(self, data, user):
        # Check before and after if we should flush.
        if self.should_flush(sys.getsizeof(data)):
            if self.should_wait_for_memory():
                self.await_free_mem()
            self.flushToFiles()
        if user not in self.audio_data:
            file = io.BytesIO()
            self.audio_data.update({user: MemoryConciousAudioData(file)})

        file = self.audio_data[user]
        file.write(data)
        if self.should_flush():
            if self.should_wait_for_memory():
                self.await_free_mem()
            self.flushToFiles()

    def cleanup(self):
        """
        Overwrites the cleanup method to flush the audio data.
        """
        self.finished = True
        self.flushToFiles(force_all=True)
        # Now wait for all the threads to finish.
        while self.write_threads:
            t, size = self.write_threads.pop()
            t.join()
        # Done!

    def any_threads_alive(self):
        if not self.write_threads:
            return False
        return any([t.is_alive() for t, _ in self.write_threads])

    def cleanup_no_flush(self):
        """
        Finishes and cleans up the audio data.
        This is a bit paranoid, but whatever.
        Wipes anything left in memory (if there is anything).
        """
        for audio_data in self.audio_data.values():
            audio_data: AudioData
            audio_data.file.seek(0)
            audio_data.file.truncate(0)
            audio_data.file.close()


class MemoryConciousDecodeManager(DecodeManager):
    def wipe_decoders(self):
        # print("Wiping decoders...")
        for decoder in self.decoder.values():
            del decoder
        self.decoder = {}

    def stop(self):
        while self.decoding:
            time.sleep(0.1)
            self.wipe_decoders()
            gc.collect()
            # print("Decoder Process Killed")
        self._end_thread.set()

    def run(self):
        n = 0
        while not self._end_thread.is_set():
            n += 1
            try:
                data = self.decode_queue.pop(0)
            except IndexError:
                time.sleep(0.001)
                continue

            try:
                if data.decrypted_data is None:
                    continue
                else:
                    data.decoded_data = self.get_decoder(data.ssrc).decode(
                        data.decrypted_data
                    )
            except OpusError:
                print("Error occurred while decoding opus frame.")
                continue

            self.client.recv_decoded_audio(data)
            if n % 10_000 == 0:
                # for every 10000 frames, wipe decoders
                self.wipe_decoders()


class MemoryConciousVoiceClient(discord.VoiceClient):
    def start_recording(
        self, sink, txtchannel, callback, *args, sync_start: bool = False
    ):
        """The bot will begin recording audio from the current voice channel it is in.
        This function uses a thread so the current code line will not be stopped.
        Must be in a voice channel to use.
        Must not be already recording.

        .. versionadded:: 2.0

        Parameters
        ----------
        sink: :class:`.Sink`
            A Sink which will "store" all the audio data.
        callback: :ref:`coroutine <coroutine>`
            A function which is called after the bot has stopped recording.
        *args:
            Args which will be passed to the callback function.
        sync_start: :class:`bool`
            If True, the recordings of subsequent users will start with silence.
            This is useful for recording audio just as it was heard.

        Raises
        ------
        RecordingException
            Not connected to a voice channel.
        RecordingException
            Already recording.
        RecordingException
            Must provide a Sink object.
        """
        if not self.is_connected():
            raise RecordingException("Not connected to voice channel.")
        if self.recording:
            raise RecordingException("Already recording.")
        if not isinstance(sink, MemoryConsiousMP3Sink):
            raise RecordingException("Must provide the MemoryConsiousMP3Sink object.")

        self.empty_socket()

        # Swap out for our own.
        # self.decoder = opus.DecodeManager(self)
        self.decoder = MemoryConciousDecodeManager(self)
        self.decoder.start()
        self.recording = True
        self.sync_start = sync_start
        self.sink: MemoryConsiousMP3Sink = sink
        self.txtchannel = txtchannel
        sink.init(self)

        t = threading.Thread(
            target=self.recv_audio,
            args=(
                sink,
                callback,
                *args,
            ),
        )
        t.start()

    def send_msg_to_txtchannel(self, msg):
        """
        Attempts to send a message to the text channel.
        Ignore if it fails.
        """
        try:
            if hasattr(self, "txtchannel"):
                asyncio.run_coroutine_threadsafe(
                    self.txtchannel.send(msg), self.loop
                ).result()
        except Exception as e:
            print(f"Failed to send message to text channel: {e}")

    def recv_audio(self, sink, callback, *args):
        """
        Overriding this, to make sure socket stays alive, instead of stopping recording.
        Might still fail of course, but we can try.
        Discords co-routines should make sure the socket stays alive, we cannot control it here.
        """
        # Gets data from _recv_audio and sorts
        # it by user, handles pcm files and
        # silence that should be added.

        self.user_timestamps: dict[int, tuple[int, float]] = {}
        self.starting_time = time.perf_counter()
        self.first_packet_timestamp: float

        sleep_time = 0.05

        sent_reconnect_msg = False
        reconnect_msg = "Connection error occurred! Trying to reconnect..."
        fail_msg = "Failed to reconnect, stopping recording."
        while self.recording:
            for _ in range(0, 10):
                try:
                    ready, _, err = select.select(
                        [self.socket], [], [self.socket], 0.01
                    )
                    if not ready:
                        if err:
                            print(f"Socket error: {err}")
                            if not sent_reconnect_msg:
                                self.send_msg_to_txtchannel(reconnect_msg)
                                sent_reconnect_msg = True

                        time.sleep(sleep_time)
                        sleep_time = sleep_time * 2
                    else:
                        sleep_time = 0.05
                        sent_reconnect_msg = False
                        break
                except ValueError:
                    # Socket has been closed.
                    print("Socket has been closed.")
                    if not sent_reconnect_msg:
                        self.send_msg_to_txtchannel(reconnect_msg)
                        sent_reconnect_msg = True
                    time.sleep(sleep_time)
                    sleep_time = sleep_time * 2
            else:
                # Didn't break, so we couldnt get a ready socket.
                print(fail_msg)
                self.send_msg_to_txtchannel(fail_msg)
                self.stop_recording()
                continue

            for _ in range(0, 10):
                try:
                    data = self.socket.recv(4096)
                    sleep_time = 0.05
                    sent_reconnect_msg = False
                    break
                except OSError as e:
                    print(f"Socket had an error, retrying... {e}")
                    if not sent_reconnect_msg:
                        self.send_msg_to_txtchannel(reconnect_msg)
                        sent_reconnect_msg = True
                    time.sleep(sleep_time)
                    sleep_time = sleep_time * 2
                    continue
            else:
                # Retry to get a ready socket?
                continue
            self.unpack_audio(data)

        self.stopping_time = time.perf_counter()
        self.sink.cleanup()
        callback = asyncio.run_coroutine_threadsafe(callback(sink, *args), self.loop)
        result = callback.result()

        if result is not None:
            print(result)

    def recv_decoded_audio(self, data: RawData):
        # Add silence when they were not being recorded.
        if data.ssrc not in self.user_timestamps:  # First packet from user
            if (
                not self.user_timestamps or not self.sync_start
            ):  # First packet from anyone
                self.first_packet_timestamp = data.receive_time
                silence = 0

            else:  # Previously received a packet from someone else
                silence = (
                    (data.receive_time - self.first_packet_timestamp) * 48000
                ) - 960

        else:  # Previously received a packet from user
            dRT = (
                data.receive_time - self.user_timestamps[data.ssrc][1]
            ) * 48000  # delta receive time
            dT = data.timestamp - self.user_timestamps[data.ssrc][0]  # delta timestamp
            diff = abs(100 - dT * 100 / dRT)
            if (
                diff > 60 and dT != 960
            ):  # If the difference in change is more than 60% threshold
                silence = dRT - 960
            else:
                silence = dT - 960

        self.user_timestamps.update({data.ssrc: (data.timestamp, data.receive_time)})

        # await user_id
        while data.ssrc not in self.ws.ssrc_map:
            time.sleep(0.05)
        user_id = self.ws.ssrc_map[data.ssrc]["user_id"]

        # Check if the silence is larger than the MAX_MB_BEFORE_FLUSH
        # (add debug 'x' to accelerate this issue triggering), this used to be a memleak here.
        # x = 10_000

        silence_length = max(0, int(silence)) * opus._OpusStruct.CHANNELS  # * x
        if silence_length > (MAX_MB_BEFORE_FLUSH * 1024 * 1024):
            # write silence in chunks of 10mb
            while silence_length != 0:
                chunk = min(silence_length, 10 * 1024 * 1024)
                self.sink.write(struct.pack("<h", 0) * chunk, user_id)
                silence_length -= chunk
        else:
            data.decoded_data = (
                struct.pack("<h", 0) * silence_length + data.decoded_data
            )
        self.sink.write(data.decoded_data, user_id)

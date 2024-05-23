import io
import os
import subprocess
import threading
from datetime import datetime

from discord.sinks import AudioData, Filters, MP3Sink, MP3SinkError

from ffmpeg_util import write_wav_btyes_to_mp3_file

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

    def __init__(self, *, filters=None, max_size_mb=100, output_folder="output"):
        super().__init__(filters=filters)
        self.max_size_mb = max_size_mb
        self.output_folder = output_folder
        os.makedirs(output_folder, exist_ok=True)

    def check_memory_size(self):
        total_size = 0
        for user_id, audio in self.audio_data.items():
            total_size += audio.file.tell()

        return total_size > self.max_size_mb * 1024 * 1024

    def flushToFile(self):
        """
        Swap out all the BytesIO objects for FileIO objects (if they're not already).
        """
        for user_id, audio in self.audio_data.items():
            if not hasattr(audio, "files_on_disk"):
                raise ValueError(
                    f"Wrong AudioData instance for {self.__class__.__name__}, needs to be MemoryConciousAudioData"
                )

            fn = f"{self.output_folder}/{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.mp3"
            audio.files_on_disk.append(fn)

            threading.Thread(
                target=write_wav_btyes_to_mp3_file,
                args=(
                    io.BytesIO(
                        audio.file.getvalue()
                    ),  # copy the BytesIO for the thread
                    fn,
                ),
            ).start()

            # now we can wipe the current BytesIO
            audio.file.seek(0)
            audio.file.truncate(0)

    def format_audio(self, audio):
        """Formats the recorded audio.
        This usually gets called when the recording is finished (sink.cleanup). but we can call it whenever we want.
        final_call is a flag to indicate if this is the final call, if it is, we'll swap out the BytesIO for FileIO.
        (so we don't need to overwrite voice_client's recv_audio).

        FIXME: probably need to use multiple files for each user, as mp3 is not a streamable format?

        Raises
        ------
        MP3SinkError
            Formatting the audio failed.
        """
        args = [
            "ffmpeg",
            "-f",
            "s16le",
            "-ar",
            "48000",
            "-loglevel",
            "error",
            "-ac",
            "2",
            "-i",
            "-",
            "-f",
            "mp3",
            "pipe:1",
        ]
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
            )
        except FileNotFoundError:
            raise MP3SinkError("ffmpeg was not found.") from None
        except subprocess.SubprocessError as exc:
            raise MP3SinkError(
                "Popen failed: {0.__class__.__name__}: {0}".format(exc)
            ) from exc

        # find user
        user_id = None
        for user_id_, audio_ in self.audio_data.items():
            if audio == audio_:
                user_id = user_id_
                break

        if user_id is None:
            # this should never happen (probably)
            raise ValueError("User not found in audio_data while formatting audio!?")

        fn = f"{self.output_folder}/{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.mp3"

        with open(fn, "wb") as f:
            f.write(process.communicate(audio.file.read())[0])

        audio.file.seek(0)
        audio.file.truncate(0)
        audio.files_on_disk.append(fn)

    @Filters.container
    def write(self, data, user):
        if user not in self.audio_data:
            file = io.BytesIO()
            self.audio_data.update({user: MemoryConciousAudioData(file)})

        file = self.audio_data[user]
        file.write(data)
        # Check if the buffer has gotten too big.
        if self.check_memory_size():
            # If it has, flush the buffer to a file.
            self.flushToFile()

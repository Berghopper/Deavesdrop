import io
import subprocess
import time


def combine_mp3_files(files: list[str], fn: str, tmp_fn: str):
    """
    Combines mp3 files into a single mp3 file.
    using ffmpeg directly. pydub, again, saves stuff in memory as wav. (yay!)
    """
    with open(tmp_fn, "w") as f:
        f.write("\n".join([f"file '{f}'" for f in files]))

    args = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", tmp_fn, "-c", "copy", fn]

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise ValueError("ffmpeg was not found.") from None
    except subprocess.SubprocessError as exc:
        raise ValueError(
            "Popen failed: {0.__class__.__name__}: {0}".format(exc)
        ) from exc

    while process.poll() is None:
        time.sleep(0.1)
        pass


def overlay_mp3_files(files: list[str], fn: str):
    """
    Overlay mp3 files into a single mp3 file with ffmpeg.

    ffmpeg -i input0.mp3 -i input1.mp3 -filter_complex amix=inputs=2:duration=longest output.mp3
    ffmpeg -i VOCALS -i MUSIC -filter_complex amix=inputs=2:duration=longest:dropout_transition=0:weights="1 0.25":normalize=0 OUTPUT

    TODO audio weights? e.g. different volume levels for different users.
    """

    args = ["ffmpeg"]

    for f in files:
        args.extend(["-i", f])

    args.extend(["-filter_complex", "amix=inputs=2:duration=longest", fn])

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise ValueError("ffmpeg was not found.") from None
    except subprocess.SubprocessError as exc:
        raise ValueError(
            "Popen failed: {0.__class__.__name__}: {0}".format(exc)
        ) from exc

    while process.poll() is None:
        time.sleep(0.1)
        pass


def write_wav_btyes_to_mp3_file(audio_dat: io.BytesIO, fn: str):
    """
    Writes wav audio data to an mp3 file.
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
        raise ValueError("ffmpeg was not found.") from None
    except subprocess.SubprocessError as exc:
        raise ValueError(
            "Popen failed: {0.__class__.__name__}: {0}".format(exc)
        ) from exc

    out = process.communicate(audio_dat.read())[0]

    with open(fn, "wb") as f:
        f.write(out)

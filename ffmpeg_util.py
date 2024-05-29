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

    return process.returncode == 0


def overlay_mp3_files(files: dict[str, int], fn: str):
    """
    Overlay mp3 files into a single mp3 file with ffmpeg.

    files is a dict of file paths and each of their weights (int 0-100), which is the volume level.

    https://ffmpeg.org/ffmpeg-filters.html#amix
    """

    args = ["ffmpeg"]

    for f in files:
        args.extend(["-i", f])

    inputs_n = len(files.keys())
    weight_str = " ".join([f"{v/100:.2f}" for v in files.values()])

    args.extend(
        [
            "-filter_complex",
            f"amix=inputs={inputs_n}:duration=longest:weights={weight_str}",
            fn,
        ]
    )

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

    return process.returncode == 0


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

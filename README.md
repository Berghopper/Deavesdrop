# Deavesdrop
(Deavesdrop = Discord + eavesdrop) 

Discord bot for recording voice channels, with the attempt of making it memory efficient.

Inspired by [the pycord voice recording example](https://github.com/Pycord-Development/pycord/blob/d0b9f5ef7861d2b23f174aa10cbea866690b4bf4/examples/audio_recording_merged.py).

Tried to run the above example on a measly Pi 3B+, which actually worked. 
However, the memory usage was quite high after longer recordings, and the bot would eventually crash, losing all the recorded audio.

Both pycord and pydub are great libraries, but they are not memory efficient enough for this use case.
So here we do some of our magic for a minimal bot that can record voice channels.

Feel free to run this bot for yourself and modify it to your needs. :).

## Small disclaimer
I'm not personally responsible for any misuse of this bot by others. This is just code, and it's up to you to use it responsibly.

## Features

- Runs bot on whitelisted text channels
- Record voice channels (but only one at a time)
- Flushes audio to disk for every ~100MB (editable in .env)
- Limits write threads to having ~200mb of audio in memory at any time (editable in .env)
- upload files to Gdrive
- add user volume weighting (e.g. lower the volume of a user/bot that is too loud)

## TBA:

- Add a better way of handling gauth.
- Add a way to convert opus straight to mp3 (instead of opus -> wav -> mp3)
- Use rust?, or some other language for the audio processing (python is not the best for this)

## Memory 'fixes'/other changes
- Skipping usage of pydub altogether, because it stores plain wav in memory while processing.
  + Instead we use ffmpeg directly
- Overriding audio sinks to flush audio to disk every ~100MB
- Making sure silence frames are batched when writing. Before if a big amount of silence was recorded, it would be instantly generated in memory, creating memory spikes.
- Using a custom voice client that wipes underlying decoders after 10k frames (causes memory leaks because c lib is not releasing memory) <- (maybe not needed?)
- Attempting to await the socket if it closes unexpectedly (not sure if this works)

## Setup

- install the required packages with `pip install -r requirements.txt`
- install ffmpeg and 7z
- create a `.env` file based on the `.env-example` file
- for the gdrive upload we need a `secrets` folder
- add `secret.json`/`token.json` to `secrets` folder so we can authenticate with bot.
  + `token.json` needs to be retrieved manually with the `gauth.py` script and authorizing the bot.
- run it!

# Known issues
Currently there's still issues with random hangs/crashes, it seems that the socket sometimes closes unexpectedly.
Pycord does not account for any of this, so it's hard to debug/fix.

## Friendly reminder

Both limit values for memory usage are attempted to be adhered, but they might not be exact.
Thus it might be good to be conservative with the values.

E.g. when using:
```
MAX_MB_BEFORE_FLUSH = "50"
MAX_MB_IN_MEM = "100"
```

At most 150MB ~should~ be in memory at any time, but it might be a bit more.
In the worst case, this was a about double the value ~150MB -> 300MB.
This is because of some overhead in some places, and I can't be bothered to find out where it is.

Recommended for a Pi 3B+ (1GB RAM):

```
MAX_MB_BEFORE_FLUSH = "100"
MAX_MB_IN_MEM = "200"
```

(Tried this, and has worked so far... but no guarantees!)

If you're running with Docker, consider setting the vars more conservatively.

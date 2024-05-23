# Deavesdrop
Discord bot for recording voice channels, with the attempt of making it memory efficient.

Inspired by [the pycord voice recording example](https://github.com/Pycord-Development/pycord/blob/d0b9f5ef7861d2b23f174aa10cbea866690b4bf4/examples/audio_recording_merged.py).

Tried to run the above example on a measly Pi 3B+, which actually worked. 
However, the memory usage was quite high after longer recordings, and the bot would eventually crash, losing all the recorded audio.

Both pycord and pydub are great libraries, but they are not memory efficient enough for this use case.
So here we do some of our magic for a minimal bot that can record voice channels.

Feel free to run this bot for yourself and modify it to your needs. :).

## Features

- Runs bot on whitelisted text channels
- Record voice channels (but only one at a time)
- Flushes audio to disk for every ~100MB (editable in .env)
- Stores files locally for now

## TBA

- upload files to Gdrive
- add user volume weighting (e.g. lower the volume of a user/bot that is too loud)

## Setup

- install the required packages with `pip install -r requirements.txt`
- install ffmpeg
- create a `.env` file based on the `.env-example` file
- run it!

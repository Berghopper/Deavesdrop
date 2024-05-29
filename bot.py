import os
import subprocess
import time
from datetime import datetime

import discord
from discord.ext import commands
from discord.sinks import MP3Sink
from dotenv import dotenv_values

from ffmpeg_util import combine_mp3_files, overlay_mp3_files
from gdrive import GoogleDriveUploader
from vc_util import MemoryConsiousMP3Sink

# globals
config = dotenv_values(".env")

TOKEN = config["TOKEN"]
CHANNEL_IDS = config["CHANNEL_IDS"].split(",")
VERSION = config["VERSION"]
MAX_MB_IN_MEM = int(config["MAX_MB_IN_MEM"])
OUTPUT_PATH = config["OUTPUT_PATH"]
BOT_NAME = config["BOT_NAME"]
OUTPUT_G_FOLDER_ID = config["OUTPUT_G_FOLDER_ID"]
GDRIVE_SECRETS_DIR = config["GDRIVE_SECRETS_DIR"]
ZIP_PASSWORD = config["ZIP_PASSWORD"]

# Setup
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# vars
connections = {}
recording = False
user_volumes = {}
# load user volumes
try:
    if os.path.exists("user_volumes.txt"):
        with open("user_volumes.txt", "r") as f:
            user_volumes = {
                int(user_id): int(volume)
                for user_id, volume in [line.split() for line in f.readlines()]
            }
except Exception as e:
    print(e)


# functions
def remove_files(files):
    for f in files:
        if not os.path.exists(f):
            continue
        try:
            os.remove(f)
        except OSError:
            pass


def zip_protect(fn: str):
    """
    Zips a file with a password. (7z)
    """
    z_name = os.path.splitext(fn)[0]
    args = ["7z", "a", f"-p{ZIP_PASSWORD}", f"{z_name}.7z", fn]
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise ValueError("zip was not found.") from None
    except subprocess.SubprocessError as exc:
        raise ValueError(
            "Popen failed: {0.__class__.__name__}: {0}".format(exc)
        ) from exc

    while process.poll() is None:
        time.sleep(0.1)
        pass

    if process.returncode == 0:
        return f"{z_name}.7z"
    return None


# checks/callbacks


async def is_correct_channel(ctx):
    if not any([ctx, ctx.channel, ctx.channel.id]):
        return False
    return str(ctx.channel.id) in CHANNEL_IDS


async def finished_callback(sink: MP3Sink, channel: discord.TextChannel):
    combind_fn = (
        f"{OUTPUT_PATH}/combined-{datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}.mp3"
    )

    await channel.send("Combining audio files of individual users...")
    tmp_files = []
    for user_id, audio in sink.audio_data.items():
        tmp_files.append(f"{OUTPUT_PATH}/temp_combine_{user_id}.txt")
        success = combine_mp3_files(
            # for this specifically we need to strip off the prepended output folder
            [x.replace(f"{OUTPUT_PATH}/", "") for x in audio.files_on_disk],
            f"{OUTPUT_PATH}/{user_id}.mp3",
            f"{OUTPUT_PATH}/temp_combine_{user_id}.txt",
        )
        if not success:
            user = await bot.fetch_user(user_id)
            await channel.send(
                f"Failed to combine audio files for {user.mention}! Stopping the process..."
            )
            remove_files(tmp_files)
            return
        else:
            remove_files(audio.files_on_disk)
    remove_files(tmp_files)

    await channel.send("Overlaying audio files...")

    inp = {}

    for user_id in sink.audio_data.keys():
        file_path = f"{OUTPUT_PATH}/{user_id}.mp3"
        if user_volumes.get(user_id, None):
            inp[file_path] = user_volumes[user_id]
        else:
            inp[file_path] = 100

    success = overlay_mp3_files(
        inp,
        combind_fn,
    )
    if not success:
        await channel.send("Failed to overlay audio files! Stopping the process...")
    else:
        remove_files(inp.keys())

    await channel.send("Done overlay! Zipping with password...")

    combined_zip_fn = zip_protect(combind_fn)
    remove_files([combind_fn])

    file_id = GoogleDriveUploader(
        f"{GDRIVE_SECRETS_DIR}/secret.json",
        token_file=f"{GDRIVE_SECRETS_DIR}/token.json",
    ).upload_resumable(combined_zip_fn, OUTPUT_G_FOLDER_ID)

    if file_id:
        remove_files([combined_zip_fn])
        await channel.send(f"Uploaded to Google Drive!")
    else:
        await channel.send("Failed to upload to Google Drive! File is on bot server.")


# events
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    # Check if the output folder exists and is empty
    if not os.path.exists(OUTPUT_PATH):
        os.makedirs(OUTPUT_PATH)
    else:
        # if files are present, alert the channel
        if os.listdir(OUTPUT_PATH):
            for channel_id in CHANNEL_IDS:
                channel = bot.get_channel(int(channel_id))
                await channel.send(
                    "The output folder is not empty, perhaps a previous recording was not finished correctly?"
                )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        print("Command was called from the abyss, no-one replied.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send(
            "Unknown command. Please query with `!help` to see the list of available commands."
        )
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "You forgot to provide some arguments. Please query with `!help` to see the list of available commands."
        )
    else:
        await ctx.send(
            "The code monkeys tried really hard to do what you wanted them to. However it seems like they liked bananas more and tore your query to shreds."
        )
        raise error


# commands
@bot.command()
async def version(ctx):
    """Command to check the bot version."""
    await ctx.send(f"{BOT_NAME} version: {VERSION}")


@bot.command()
async def join(ctx: discord.ApplicationContext):
    """Join the voice channel!"""
    voice = ctx.author.voice

    if not voice:
        await ctx.send("You're not in a vc right now")
        return

    await voice.channel.connect()

    await ctx.send("Joined!")


@bot.command()
async def start(ctx: discord.ApplicationContext):
    """Record the voice channel!"""
    global recording
    voice = ctx.author.voice

    if not voice:
        return await ctx.send("You're not in a vc right now")

    vc: discord.VoiceClient = ctx.voice_client

    if not vc:
        return await ctx.send("I'm not in a vc right now. Use `!join` to make me join!")

    if recording:
        return await ctx.send(
            "I'm already recording in another channel! Can't record in multiple channels at once."
        )

    recording = True

    vc.start_recording(
        MemoryConsiousMP3Sink(max_size_mb=MAX_MB_IN_MEM, output_folder=OUTPUT_PATH),
        finished_callback,
        ctx.channel,
        sync_start=True,
    )

    await ctx.send("The recording has started!")


@bot.command()
async def stop(ctx: discord.ApplicationContext):
    """Stop the recording"""
    global recording
    vc: discord.VoiceClient = ctx.voice_client

    if not vc:
        return await ctx.send("There's no recording going on right now")

    vc.stop_recording()
    recording = False

    await ctx.send("The recording has stopped!")


@bot.command()
async def leave(ctx: discord.ApplicationContext):
    """Leave the voice channel!"""
    vc: discord.VoiceClient = ctx.voice_client

    if not vc:
        return await ctx.send("I'm not in a vc right now")

    await vc.disconnect()

    await ctx.send("Left!")


@bot.command()
async def setvol(ctx: discord.ApplicationContext, user: discord.User, volume: int):
    """!setvol <user> <volume>. Set the volume of the user in the command.
    volume must be between 0 and 100."""
    if volume < 0 or volume > 100:
        await ctx.send("Volume must be between 0 and 100.")
        return
    user_volumes[user.id] = volume
    # write to file
    with open("user_volumes.txt", "w") as f:
        f.write(
            "\n".join(
                [f"{user_id} {volume}" for user_id, volume in user_volumes.items()]
            )
        )
    await ctx.send(f"Volume set for {user.name} to {volume}.")


@bot.command()
async def getvols(ctx: discord.ApplicationContext):
    """!getvols. Get the edited volumes of the users. (if not set, defaults to 100)"""
    for user_id, volume in user_volumes.items():
        user = await bot.fetch_user(user_id)
        await ctx.send(f"{user.mention}: {volume}")


@bot.command()
async def resetvols(ctx: discord.ApplicationContext):
    """!resetvols. Reset the edited volumes of the users."""
    global user_volumes
    user_volumes = {}
    # delete the file
    remove_files(["user_volumes.txt"])
    await ctx.send("Volumes reset.")


bot.add_check(is_correct_channel)
bot.run(TOKEN)

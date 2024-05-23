import discord
from discord.ext import commands
from discord.sinks import MP3Sink
from dotenv import dotenv_values

from ffmpeg_util import combine_mp3_files, overlay_mp3_files
from vc_util import MemoryConsiousMP3Sink

# globals
config = dotenv_values(".env")

TOKEN = config["TOKEN"]
CHANNEL_IDS = config["CHANNEL_IDS"].split(",")
VERSION = config["VERSION"]
MAX_MB_IN_MEM = int(config["MAX_MB_IN_MEM"])
OUTPUT_PATH = config["OUTPUT_PATH"]
BOT_NAME = config["BOT_NAME"]

# Setup
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# vars
connections = {}


async def is_correct_channel(ctx):
    if not any([ctx, ctx.channel, ctx.channel.id]):
        return False
    return str(ctx.channel.id) in CHANNEL_IDS


async def finished_callback(sink: MP3Sink, channel: discord.TextChannel):
    for user_id, audio in sink.audio_data.items():
        combine_mp3_files(
            # for this specifically we need to strip off the prepended output folder
            [x.replace(f"{OUTPUT_PATH}/", "") for x in audio.files_on_disk],
            f"{OUTPUT_PATH}/{user_id}.mp3",
            f"{OUTPUT_PATH}/temp_combine_{user_id}.txt",
        )
    overlay_mp3_files(
        [f"{OUTPUT_PATH}/{user_id}.mp3" for user_id in sink.audio_data.keys()],
        f"{OUTPUT_PATH}/combined.mp3",
    )

    await channel.send("done")


# events
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        print("Command was called from the abyss, no-one replied.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send(
            "Unknown command. Please query with `!help` to see the list of available commands."
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
async def record(ctx: discord.ApplicationContext):
    """Record the voice channel! (synonym for !start)"""
    await start(ctx)


@bot.command()
async def start(ctx: discord.ApplicationContext):
    """Record the voice channel!"""
    voice = ctx.author.voice

    if not voice:
        return await ctx.send("You're not in a vc right now")

    vc: discord.VoiceClient = ctx.voice_client

    if not vc:
        return await ctx.send("I'm not in a vc right now. Use `!join` to make me join!")

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
    vc: discord.VoiceClient = ctx.voice_client

    if not vc:
        return await ctx.send("There's no recording going on right now")

    vc.stop_recording()

    await ctx.send("The recording has stopped!")


@bot.command()
async def leave(ctx: discord.ApplicationContext):
    """Leave the voice channel!"""
    vc: discord.VoiceClient = ctx.voice_client

    if not vc:
        return await ctx.send("I'm not in a vc right now")

    await vc.disconnect()

    await ctx.send("Left!")


bot.add_check(is_correct_channel)
bot.run(TOKEN)

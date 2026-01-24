import asyncio
import atexit
import os
import signal
from typing import Any
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path

from loguru import logger

from components.sable import Sable

# ---- globals ----
global shutdown_flag

SABLES_FAV_COLOUR = discord.Colour(0x0077BE)
discord_data: dict[int, Any] = {}
MAX_HISTORY_PER_CHANNEL = 100

shutdown_flag = False

# ---- logging ----
PATH_ROOT: Path = Path(__file__).resolve().parent
LOG_PATH: Path = PATH_ROOT / "logs" / "Sable.logs"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logger.add(
    LOG_PATH, 
    rotation='100 MB', 
    enqueue=True, 
    compression='zip', 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ---- env ----
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(env_path)

# ---- client ----
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---- AI core ----
BOT_ID = int(os.getenv("BOT_ID"))
sable = Sable(BOT_ID)

# ---- Utilities ----

def permission_check(author: discord.Member) -> bool:
    return author.guild_permissions.administrator

def get_channel_data(guild_id: int, channel_id: int) -> dict:
    """Safe getter for channel data, initializes if missing."""
    guild_data = discord_data.setdefault(guild_id, {})
    channel_data = guild_data.setdefault(channel_id, {
        'text_channel': None,
        'messages': [],
        'lock': asyncio.Lock()
    })
    return channel_data

def store_text_message(message: discord.Message):
    channel_data = get_channel_data(message.guild.id, message.channel.id)
    messages = channel_data['messages']
    messages.append(message)
    if len(messages) > MAX_HISTORY_PER_CHANNEL:
        messages.pop(0)

def unstore_text_message(message: discord.Message):
    channel_data = discord_data.get(message.guild.id, {}).get(message.channel.id)
    if not channel_data:
        return
    messages = channel_data.get('messages', [])
    if message in messages:
        messages.remove(message)

async def store_text_channel(channel: discord.TextChannel, limit=MAX_HISTORY_PER_CHANNEL):
    perms = channel.permissions_for(channel.guild.me)
    if not perms.read_message_history:
        logger.warning(f"Attempted to read message history of channel {channel.id} without sufficent permissions.")
        return

    channel_data = get_channel_data(channel.guild.id, channel.id)
    channel_data['text_channel'] = channel
    channel_data['messages'].clear()  # reset

    try:
        async for message in channel.history(limit=limit, oldest_first=False):
            store_text_message(message)
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.exception(f"Could not fetch history for {channel}: {e}")

def unstore_channel(channel: discord.TextChannel):
    guild_data = discord_data.get(channel.guild.id)
    if guild_data:
        guild_data.pop(channel.id, None)

async def store_guild(guild: discord.Guild):
    discord_data.setdefault(guild.id, {})
    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel):
            await store_text_channel(channel)

def unstore_guild(guild: discord.Guild):
    discord_data.pop(guild.id, None)

def allow_reply(message: discord.Message) -> bool:
    """Reply only if bot is mentioned."""
    return message.guild.me in message.mentions if message.mentions else False

# ---- Bot Events ----

@bot.event
async def on_ready():
    print(f"I am logged in as {bot.user}!")
    for guild in bot.guilds:
        await store_guild(guild)
    await sable.async_init()

@bot.event
async def on_guild_join(guild: discord.Guild):
    await store_guild(guild)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.content.strip():
        return

    store_text_message(message)

    if not allow_reply(message):
        return

    channel_data = get_channel_data(message.guild.id, message.channel.id)

    async with channel_data['lock']:
        async with message.channel.typing():
            try:
                reply_text = await sable.reply(channel_data)
            except Exception as e:
                logger.exception(f"Failed to generate a reply: {e}")
                reply_text = "Sorry, I couldn't generate a reply."

        reply = await message.reply(reply_text)
        store_text_message(reply)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before == after:
        return
    unstore_text_message(before)
    store_text_message(after)

@bot.event
async def on_message_delete(message: discord.Message):
    unstore_text_message(message)

@bot.event
async def on_guild_channel_update(before, after):
    if before == after:
        return
    unstore_channel(before)
    if isinstance(after, discord.TextChannel):
        await store_text_channel(after)

@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    if before == after:
        return
    unstore_guild(before)
    await store_guild(after)

@bot.event
async def on_guild_channel_delete(channel):
    unstore_channel(channel)

@bot.event
async def on_guild_remove(guild: discord.Guild):
    unstore_guild(guild)

# ---- Shutdown ----
@logger.catch(level='CRITICAL', message="Failed to shutdown")
async def safe_shutdown():
    global shutdown_flag
    
    if shutdown_flag:
        logger.info("Shutdown called during shutdown")
        return
    shutdown_flag = True

    await sable.async_close()
    await bot.close()
    
def request_shutdown():
    loop = asyncio.get_event_loop()

    if loop.is_running():
        asyncio.run_coroutine_threadsafe(safe_shutdown(), loop)
    else:
        asyncio.run(safe_shutdown())    
    
@bot.slash_command(name="shutdown")
async def shutdown_command(interaction: discord.Interaction):
    if not permission_check(interaction.user):
        await interaction.response.send_message(
            "You are not authorized to shut me down.", ephemeral=True
        )
        logger.info(f"The user {interaction.user.id} was blocked from running the shutdown command")
        return

    await interaction.response.send_message(
        "Shutting down...", ephemeral=True
    )
    logger.info(f"The user {interaction.user.id} executed the shutdown command")
    await safe_shutdown()

def shutdown_signal(sig, frame):
    logger.info("Signal received, shutting down...")
    request_shutdown()

# ---- Run Bot ----

if __name__ == "__main__":
    BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not BOT_TOKEN:
        logger.critical("DISCORD_BOT_TOKEN not found in .env")
        raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")

    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, shutdown_signal)
    atexit.register(request_shutdown)

    bot.run(BOT_TOKEN)
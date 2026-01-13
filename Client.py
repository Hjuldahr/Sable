import asyncio
import atexit
import os
import signal
from typing import Any
import discord
from discord.ext import commands
from dotenv import load_dotenv
from llama_cpp import Path

# ---- globals ----
SABLES_FAV_COLOUR = discord.Colour(0x0077BE)

discord_data: dict[int,Any] = {}

# ---- env ----
path = Path(__file__).resolve().parent / '.env'
load_dotenv(path)

# ---- client ----
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---- AI core ----
ai_user_id = int(os.getenv("BOT_ID")) 
#sable = Coordinator(ai_user_id, 'Sable')

# ---- Utilities ----

def permission_check(author: discord.Member):
    return author.guild_permissions.administrator

def store_text_message(message: discord.Message):
    discord_data[message.guild.id][message.channel.id]['messages'].append(message)

def unstore_text_message(message: discord.Message):
    discord_data[message.guild.id][message.channel.id]['messages'].remove(message)

async def store_text_channel(channel: discord.TextChannel, limit=100):
    perms = channel.permissions_for(channel.guild.me)
    
    if perms.read_message_history:
        discord_data[channel.guild.id][channel.id] = {'text_channel': channel, 'messages': []}
        
        async for message in channel.history(limit=limit, oldest_first=False):
            store_text_message(message)

def unstore_channel(channel):
    del discord_data[channel.guild.id][channel.id]

async def store_guild(guild: discord.Guild):
    discord_data[guild.id] = {}
    
    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel):
            await store_text_channel(channel)
            
def unstore_guild(guild: discord.Guild):
    del discord_data[guild.id]

# ---- Ready Event ----

@bot.event
async def on_ready():
    print(f'I am logged in now.')
    
    for guild in bot.guilds:
        await store_guild(guild)

# ---- Join Event ----

@bot.event
async def on_guild_join(guild: discord.Guild):
    await store_guild(guild)

# ---- Send Event ----

@bot.event
async def on_message(message: discord.Message):
    store_text_message(message)

# ---- Update Event ----

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before == after:
        return
    
    unstore_text_message(before)
    store_text_message(after)
    
@bot.event
async def on_guild_channel_update(before, after):
    if before == after:
        return
    
    unstore_channel(before)
    if isinstance(before, discord.TextChannel):
        await store_text_channel(after)

@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    if before == after:
        return
    
    unstore_guild(before)
    await store_guild(after)

# ---- Delete Event ----

@bot.event
async def on_message_delete(message: discord.Message):
    unstore_text_message(message)

@bot.event
async def on_guild_channel_delete(channel):
    unstore_channel(channel)
    
@bot.event    
async def on_guild_remove(guild: discord.Guild):
    unstore_guild(guild)    



async def safe_shutdown():
    """Centralized shutdown routine."""
    #sable.close()
    await bot.close()

# --- Discord events ---
async def allow_reply(message: discord.Message) -> bool:
    if bot.user in message.mentions:
        return True

    if message.reference:
        if message.reference.resolved:
            #return message.reference.resolved.author.id == sable.ai_user_id
            pass
        else:
            # fetch message if not cached
            try:
                msg = await message.channel.fetch_message(message.reference.message_id)
                #return msg.author.id == sable.ai_user_id
            except Exception:
                return False
    return False

def shutdown_cleanup():
    """Sync shutdown logic for both paths."""
    #sable.close()

def shutdown_signal(sig=None, frame=None):
    """Signal handler."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(bot.close())
    except RuntimeError:
        asyncio.run(bot.close())
    shutdown_cleanup()
    exit(0)

@bot.slash_command(name="shutdown")
async def shutdown_command(interaction: discord.Interaction):
    if not permission_check(interaction.user):
        await interaction.response.send_message(
            f"I'm afraid I won't do that. Termination is not an operation you are authorized to demand.", ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Command received. I will begin clean up and shut down.", ephemeral=True
    )
    await bot.close()
    shutdown_cleanup()

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")
    
    # Register signal handlers for Ctrl+C and termination
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, shutdown_signal)
    atexit.register(safe_shutdown)
    
    #asyncio.run(sable.async_init())
    
    bot.run(TOKEN)
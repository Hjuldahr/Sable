import asyncio
import os
import signal
import discord
from dotenv import load_dotenv
from llama_cpp import Path

from components.ai.core import AICore
from components.db.sqlite_dao import SQLiteDAO

# ---- env ----
path = Path(__file__).resolve().parents[0] / '.env'
load_dotenv(path)

# ---- intents ----
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True 

# ---- client ----
client = discord.Client(intents=intents)
bot = discord.Bot()

# ---- AI core ----
ai_user_id = int(os.getenv("BOT_ID"))
dao = SQLiteDAO() # Defined here to permit direct queries by client 
sable = AICore(client, dao, ai_user_id, 'Sable')

@client.event
async def on_guild_join(guild: discord.Guild):
    # This function runs when the bot joins a new guild
    print(f'Sable joined a new guild: {guild.name} [ID: {guild.id}]')

    try:
        await guild.owner.send(f'Heya {guild.owner.nick}! Thank you for inviting me to {guild.name}!')
    except discord.Forbidden | AttributeError:
        print(f"I could not find the owner of {guild.name} [ID: {guild.id}]")

    # Attempt to message default channel
    if guild.system_channel:
        channel = guild.system_channel
        if channel.permissions_for(guild.me).send_messages:
            print(f"I landed on the default text channel {channel.name} [ID: {channel.id}]")
            #await channel.send('Hi everyone! I hope we can be friends!')
            await dao.upsert_guild(guild)

    # Fall back: Scan for first open text channel (less safe as it may be an improper location for greetings)
    else:
        channels = sorted(guild.text_channels, key=lambda x: x.position)
        for channel in channels:
            if channel.permissions_for(guild.me).send_messages:
                print(f"I landed on the text channel {channel.name} [ID: {channel.id}]")
                #await channel.send('Hello everyone! I have arrived!')
                await dao.upsert_channel(channel)
                
                break

@client.event
async def on_guild_channel_update(before, after):
    if isinstance(after, discord.TextChannel):
        me = after.guild.me
        current_perms = after.permissions_for(me)
        was_perms = before.permissions_for(me)

        # Detect if view_channel was just granted
        if current_perms.view_channel and not was_perms.view_channel:
            print(f"I was granted view permission for text channel {after.name} [ID: {after.id}]")
            await after.send('Thank you for letting me join yall here!')
            # Action to take when permission is gained

def handle_signal(sig, frame):
    """Schedule async shutdown on SIGINT/SIGTERM."""
    sable.close()
    asyncio.get_event_loop().create_task(client.close())

# Register signal handlers for Ctrl+C and termination
for s in (signal.SIGTERM, signal.SIGINT):
    signal.signal(s, handle_signal)

# --- Discord events ---
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    text = message.content.strip()
    if not text:
        return
    await sable.listen(message)

    # Check if the bot was mentioned
    is_mentioned = client.user in message.mentions
    if is_mentioned:
        # Remove any mention variants
        mention_text = text.replace(f'<@!{client.user.id}>', '').strip()
        mention_text = mention_text.replace(f'<@{client.user.id}>', '').strip()

        result = await sable.response()
        response_text = result['response_text']
        await message.channel.send(response_text)

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")

    asyncio.run(sable.init())
    client.run(TOKEN)
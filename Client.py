import asyncio
import os
import signal
import discord
from dotenv import load_dotenv
from llama_cpp import Path

from components.ai.Core import Core

path = Path(__file__).resolve().parents[0] / '.env'
load_dotenv(path)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

ai_user_id = int(os.getenv("BOT_ID"))
sable = Core(client, ai_user_id, 'Sable')

# --- Async startup task ---
async def startup():
    """Initialize async resources before bot starts."""
    await sable.init() 
    print("Discord Client Starting Up")

# --- Graceful shutdown ---
async def shutdown():
    print("Discord Client Shutting Down")

def handle_signal(sig, frame):
    """Schedule async shutdown on SIGINT/SIGTERM."""
    sable.close()
    asyncio.get_event_loop().create_task(client.close())
    exit(0)

# Register signal handlers for Ctrl+C and termination
for s in (signal.SIGTERM, signal.SIGINT):
    signal.signal(s, handle_signal)

# --- Discord events ---
@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    # Ensure EOS is initialized
    await startup()

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

    client.run(TOKEN)
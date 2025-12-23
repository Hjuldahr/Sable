import os
import signal
import discord
from dotenv import load_dotenv

from components.ai.Core import Core

load_dotenv(r'.\SABLE\.env')

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

sable = Core('Sable', 1452493514050113781)

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
    client.close() 

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

    reactions = message.reactions

    # Check if the bot was mentioned
    is_mentioned = client.user in message.mentions
    if is_mentioned:
        # Remove any mention variants
        mention_text = text.replace(f'<@!{client.user.id}>', '').strip()
        mention_text = mention_text.replace(f'<@{client.user.id}>', '').strip()

        if mention_text:
            reply = await sable.listen_respond(
                channel_id=message.channel.id,
                channel_name=message.channel.name,
                message_id=message.id,
                query_timestamp=message.created_at,
                user_id=message.author.id,
                user_name=message.author.name,
                query=mention_text
            )
        else:
            reply = await sable.respond()

        await message.channel.send(reply)
    else:
        await sable.listen(
            channel_id=message.channel.id,
                channel_name=message.channel.name,
                message_id=message.id,
                query_timestamp=message.created_at,
                user_id=message.author.id,
                user_name=message.author.name,
                query=text
        )

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")

    client.run(TOKEN)
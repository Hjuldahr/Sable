import discord
import os
from dotenv import load_dotenv
import signal
from SABLE.sable_ai_v1_1 import Sable # your updated EOS class

load_dotenv(r'.\EOS\.env')

# --- Discord client setup ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

sable = Sable('Sable', 1452493514050113781)  # if EOS has async init, we call it below

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

# --- Run the bot ---
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")

    client.run(TOKEN)
    
# Goals by priority
# Persona
# 1. persistant personality formation
# 2. see & add reactions to messages it likes
# 3. use emotional analysis to dynamic adjust instructions for variable mood and tone
# Power
# 4. semantic (vector) analysis for smart context retrieval instead of raw chronology across channels
# 5. read file attachments (+images) as markdown using markitdown
# 6. web look up for knowledge base enrichment
# 7. file generation (provided via ai message attachement)
# Prestige
# 8. inviteable to calls with tts and voice recog i/o
import asyncio
from collections import deque
import os
import signal
import discord
from dotenv import load_dotenv
from llama_cpp import Path

from components.core.coordinator import Coordinator

# ---- env ----
path = Path(__file__).resolve().parents[0] / '.env'
load_dotenv(path)

# ---- client ----
intents = discord.Intents.all()
client = discord.Client(intents=intents)

# ---- AI core ----
ai_user_id = int(os.getenv("BOT_ID")) 
sable = Coordinator(ai_user_id, 'Sable')

@client.event
async def on_guild_join(guild: discord.Guild):
    # This function runs when the bot joins a new guild
    guild_dict = {
        'id': guild.id,
        'name': guild.name,
        'description': guild.description or 'No description provided',
        'created_at': guild.created_at,
        'nsfw_level': guild.nsfw_level.name,
        'verification_level': guild.verification_level.name,
        'filesize_limit': guild.filesize_limit
    }
    await sable.dao.upsert_guild()
    print(f'I joined a new guild: {guild.name} [ID: {guild.id}]')

    # UNDECIDED Remove if more annoying than endearing
    try:
        # TODO replace with generated salutation
        await guild.owner.send(f'Heya {guild.owner.nick}! Thank you for inviting me to {guild.name}!')
    except discord.Forbidden | AttributeError:
        print(f"I could not find the owner of {guild.name} [ID: {guild.id}]")

    for channel in guild.channels:
        permissions = channel.permissions_for(guild.me)
        if permissions.read_message_history and permissions.read_messages:
            channel_dict = {
                'id': channel.id,
                'guild_id': channel.guild.id,
                'name': channel.name,
                'topic': channel.topic or 'No topic provided',
                'type': channel.type.name,
                'is_nsfw': channel.is_nsfw,
                'created_at': channel.created_at,
                'permissions': {flag_name: value for flag_name, value in permissions}
            }
            await sable.dao.upsert_channel(channel_dict)

    # Attempt to message default channel
    if guild.system_channel:
        channel = guild.system_channel
        permissions = channel.permissions_for(guild.me)
        if permissions.send_messages:
            print(f"I announced my arrival at {guild.name} via '{channel.name}' [ID: {channel.id}]")
            # TODO replace with generated salutation
            await channel.send('Hi everyone! I hope we can be friends!')
            #await dao.upsert_guild(guild)

    # Fall back: Scan for first open text channel (less safe as it may be an improper location for greetings)
    else:
        channels = sorted(guild.text_channels, key=lambda x: x.position)
        for channel in channels:
            permissions = channel.permissions_for(guild.me)
            if permissions.send_messages:
                channel_dict = {
                    'id': channel.id,
                    'guild_id': channel.guild.id,
                    'name': channel.name,
                    'topic': channel.topic or 'No topic provided',
                    'type': channel.type.name,
                    'is_nsfw': channel.is_nsfw,
                    'created_at': channel.created_at
                }
                await sable.dao.upsert_channel(channel_dict)
                print(f"I announced my arrival at {guild.name} via '{channel.name}' [ID: {channel.id}]")
                # TODO replace with generated salutation
                await channel.send('Hello everyone! I have arrived!')
                break

@client.event
async def on_guild_remove(guild: discord.Guild):
    # Attempt to message default channel
    if guild.system_channel:
        channel = guild.system_channel
        if channel.permissions_for(guild.me).send_messages:
            # TODO replace with generated goodbye
            print(f"I announced my departure from {guild.name} via '{channel.name}' [ID: {channel.id}]")
            await channel.send('I am sorry if I had done something wrong. I hope I can come back in the future. But until then goodbye everyone!')

    # Fall back: Scan for first open text channel (less safe as it may be an improper location for greetings)
    else:
        channels = sorted(guild.text_channels, key=lambda x: x.position)
        for channel in channels:
            if channel.permissions_for(guild.me).send_messages:
                print(f"I announced my departure from {guild.name} via '{channel.name}' [ID: {channel.id}]")
                # TODO replace with generated goodbye
                await channel.send('I am sorry if I had done something wrong. I hope I can come back in the future. But until then goodbye everyone!')
                break
            
    await sable.dao.remove_guild(guild.id)

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
    print(f'I logged in as [Client: {client.user}]')

async def allow_reply(message: discord.Message) -> bool:
    if client.user in message.mentions:
        return True

    ref = message.reference
    if ref:
        if ref.resolved:
            return ref.resolved.author.id == sable.ai_user_id
        else:
            # fetch message if not cached
            try:
                msg = await message.channel.fetch_message(ref.message_id)
                return msg.author.id == sable.ai_user_id
            except Exception:
                return False
    return False

@client.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.content.strip():
        return
    
    await sable.read(message) # Absorb context passively
    
    # TODO add heuristic scoring for an unprompted response
    
    if allow_reply(message):
        reply_content = await sable.write(message) # contribute reactively
        
        # NOTE Set to silent if the notification feels more annoying then helpful
        await message.reply(content=reply_content, silent=False)

@client.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or before.content == after.content:
        return
    
    await sable.listen(after)

@client.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    message = reaction.message
    sable.dao.update_message_reactions(message.id,message.reactions)
    
    print(f"{user.id} reacted with {reaction.emoji} on {reaction.message.id}")

@client.event
async def on_reaction_remove(reaction: discord.Reaction, user: discord.User):
    message = reaction.message
    sable.dao.update_message_reactions(message.id,message.reactions)
    
    print(f"{user.id} retracted {reaction.emoji} for {reaction.message.id}")

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if any(payload.message_id == msg.id for msg in client.cached_messages):
        return

    channel = await client.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    sable.dao.update_message_reactions(payload.message_id, message.reactions)
    
    print(f"{payload.user_id} reacted with {payload.emoji} on {payload.message_id}")
    
@client.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if any(payload.message_id == msg.id for msg in client.cached_messages):
        return

    channel = await client.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    sable.dao.update_message_reactions(payload.message_id, message.reactions)
    
    print(f"{payload.user_id} retracted {payload.emoji} on {payload.message_id}")
    
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")
    asyncio.run(sable.runtime_setup())
    client.run(TOKEN)
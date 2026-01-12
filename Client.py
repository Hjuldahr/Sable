import asyncio
import atexit
from datetime import datetime, timezone
import io
import os
import random
import re
import signal
import discord
from discord.ext import commands
from dotenv import load_dotenv
from llama_cpp import Path

from components.ai.moods import Moods
from components.core.coordinator import Coordinator
from components.discord.discord_utilities import DiscordUtilities

SABLES_FAV_COLOUR = discord.Colour(0x0077BE)

# ---- env ----
path = Path(__file__).resolve().parent / '.env'
load_dotenv(path)

# ---- client ----
intents = discord.Intents.all()
#client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="!", intents=intents)
bot.col

# ---- AI core ----
ai_user_id = int(os.getenv("BOT_ID")) 
sable = Coordinator(ai_user_id, 'Sable')

# ---- regex ----
TEXT_DISTILLATION_REGEX = re.compile(r'(\W+|<[@#][!&]?\d{17,20}>|@everyone|@here)+')
TABLE_NAME_REGEX = re.compile(r'(?<!^)([A-Z])')

@bot.command()
@commands.is_owner()
async def sync(ctx):
    """push your local slash commands to Discord's servers""" 
    
    await bot.tree.sync()
    await ctx.send("Slash commands synchronized")
    print("Slash commands synchronized")

def permission_check(author: discord.Member):
    return author.guild_permissions.administrator

@bot.event
async def on_ready():
    print(f'I am logged in now.')

@bot.event
async def on_guild_join(guild: discord.Guild):
    # This function runs when the bot joins a new guild
    await sable.dao.upsert_guild(guild)
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
            await sable.dao.upsert_text_channel(channel, permissions)

    # Attempt to message default channel
    if guild.system_channel:
        channel = guild.system_channel
        permissions = channel.permissions_for(guild.me)
        if permissions.send_messages and permissions.read_messages:
            print(f"I announced my arrival at {guild.name} via '{channel.name}' [ID: {channel.id}]")
            # TODO replace with generated salutation
            await channel.send('Hi everyone! I hope we can be friends!')

    # Fall back: Scan for first open text channel (less safe as it may be an improper location for greetings)
    else:
        for channel in guild.text_channels:
            permissions = channel.permissions_for(guild.me)
            if permissions.send_messages and permissions.read_messages:
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

@bot.event
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

    await sable.dao.delete_guild(guild.id)

@bot.event
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

async def safe_shutdown():
    """Centralized shutdown routine."""
    sable.close()
    await bot.close()

# --- Discord events ---
@bot.event
async def on_ready():
    print(f'I have logged in as [Client: {bot.user}]')
    
    for guild in bot.guilds:
        role = discord.utils.get(guild.roles, name=bot.user.name)
        role.colour = SABLES_FAV_COLOUR

async def allow_reply(message: discord.Message) -> bool:
    if bot.user in message.mentions:
        return True

    if message.reference:
        if message.reference.resolved:
            return message.reference.resolved.author.id == sable.ai_user_id
        else:
            # fetch message if not cached
            try:
                msg = await message.channel.fetch_message(message.reference.message_id)
                return msg.author.id == sable.ai_user_id
            except Exception:
                return False
    return False

@bot.event
async def on_message(received_message: discord.Message):
    if received_message.author.bot:
        return
    
    if not DiscordUtilities.is_mention_only(received_message.content):
        await sable.read(received_message) # Absorb context passively
    
    #await message.channel.send_sound(), tts
    
    # TODO add heuristic scoring for an unprompted response
    if False == True:
        async with received_message.channel.typing():
            send_content, token_count = await sable.write(received_message) # contribute proactively
            
        sent_message = await received_message.channel.send(send_content, silent=False)
    
    elif allow_reply(received_message):
        async with received_message.channel.typing():
            reply_content, token_count = await sable.write(received_message) # contribute reactively
        
        # NOTE Set to silent if the notification feels more annoying then helpful
        sent_message = await received_message.reply(reply_content, silent=False)
        
    await sable.dao.upsert_message(sent_message, token_count)
    
    print(f"{received_message.author.id} sent the text message {received_message.id}")

def compare_messages(a: discord.Message, b: discord.Message) -> bool:
    """Ignore edits that only change whitespace, capitalization, or mentions."""
    return TEXT_DISTILLATION_REGEX.sub('', a.content.lower()) == TEXT_DISTILLATION_REGEX.sub('', b.content.lower())

# Will remove if it the sense of artificility (not human enough) outweighs the functional benifits
@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    # Ignore edits to bot messages or trivial edits
    if before.author.bot or compare_messages(before, after):
        return

    await sable.listen(after) # Process the new message content

    print(f"{after.author.id} edited the message {before.id}")

@bot.event
async def on_message_delete(message: discord.Message):
    # Remove the user message from DB
    await sable.dao.delete_message(message.id)

    # Look up AI reply directly
    ai_reply = await sable.dao.select_reply(sable.ai_user_id, message.id)
    if ai_reply is None or ai_reply['references_message_id'] == -1:
        return
    ai_reply_id = ai_reply['references_message_id']

    try:
        ai_reply = await message.channel.fetch_message(ai_reply_id)
        await ai_reply.delete(delay=random.uniform(0.25, 0.75))
        await sable.dao.delete_message(ai_reply_id)
        print(f"{message.author.id} deleted the message {message.id}")
        
    except discord.NotFound:
        await sable.dao.delete_message(ai_reply_id)
        
    except Exception as e:
        print(f"Failed to delete AI reply {ai_reply_id}: {e}")

@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    message = reaction.message
    sable.dao.update_message_reactions(message.id,message.reactions)
    
    print(f"{user.id} reacted with {reaction.emoji} on {reaction.message.id}")

@bot.event
async def on_reaction_remove(reaction: discord.Reaction, user: discord.User):
    message = reaction.message
    sable.dao.update_message_reactions(message.id,message.reactions)
    
    print(f"{user.id} retracted {reaction.emoji} for {reaction.message.id}")

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if any(payload.message_id == msg.id for msg in bot.cached_messages):
        return

    channel = await bot.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    sable.dao.update_message_reactions(payload.message_id, message.reactions)
    
    print(f"{payload.user_id} reacted with {payload.emoji} on {payload.message_id}")
    
@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if any(payload.message_id == msg.id for msg in bot.cached_messages):
        return

    channel = await bot.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    sable.dao.update_message_reactions(payload.message_id, message.reactions)
    
    print(f"{payload.user_id} retracted {payload.emoji} on {payload.message_id}")

def process_table_name(table_name: str) -> str:
    # (?<!^)([A-Z])
    return TABLE_NAME_REGEX.sub(r' \1', table_name)

@bot.tree.command(name="brief", description="Get Sable's current status")
async def brief_command(interaction: discord.Interaction):
    row_counts = await sable.dao.count_rows() or {}
    vad = sable.vad
    mood_label = Moods.ordinal(Moods.label_mood(vad))

    names = sorted(row_counts.keys(), key=lambda k: (-row_counts[k], k))
    row_counts_str = "\n".join(f"{process_table_name(name)}: {row_counts[name]:,}" for name in names) or "No Tables Found…"

    embed = discord.Embed(
        title="Sable Brief",
        description="My current status.",
        color=SABLES_FAV_COLOUR,
        timestamp=datetime.now(tz=timezone.utc)
    )
    embed.add_field(name="Mood", value=mood_label)
    embed.add_field(name="Valence", value=f"{vad.valence:.2f}")
    embed.add_field(name="Arousal", value=f"{vad.arousal:.2f}")
    embed.add_field(name="Dominance", value=f"{vad.dominance:.2f}")
    embed.add_field(name="Memory Counts", value=row_counts_str, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="memout", description="Export DB contents as a .sqlite file")
async def export_memory_command(interaction: discord.Interaction):
    if not permission_check(interaction.user):
        await interaction.response.send_message(
            f"I don't want to share that with you.", ephemeral=True
        )
        return
    
    buffer = await sable.dao.dump()
    
    if buffer:
        now = datetime.now().strftime("%Y%m%dT%H%M%S")
        filename = f"Sable_Memories_{now}.sqlite"
        file = discord.File(buffer, filename)
        
        await interaction.response.send_message(
            "Done! The attachment contains all I know.",
            file=file,
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "I am sorry to disappoint you. But, I seem to be having issues recalling my memories.",
            ephemeral=True
        )

def shutdown_cleanup():
    """Sync shutdown logic for both paths."""
    sable.close()

def shutdown_signal(sig=None, frame=None):
    """Signal handler."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(bot.close())
    except RuntimeError:
        asyncio.run(bot.close())
    shutdown_cleanup()
    exit(0)

@bot.tree.command(name="shutdown")
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
    
    asyncio.run(sable.async_init())
    
    bot.run(TOKEN)
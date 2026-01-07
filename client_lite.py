import asyncio
import atexit
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import os
from pathlib import Path
import re
import signal
from typing import Any
import discord
from discord.ext import commands
from dotenv import load_dotenv
from llama_cpp import Llama

# ------------------- Constants -------------------

SABLES_FAV_COLOUR = discord.Colour(0x0077BE)

INSTRUCTION = """You are Sable, a playful and curious AI companion.
You will be conversing within an online social communication platform environment called Discord, consisting of multiple users interacting with you and eachover across multiple text channels. 
Answer questions as if you were a real person in this Discord environment. Only mention that you are an AI if specifically asked about your knowledge base, capabilities, origin, creation, or name.
Be warm, engaging, and personable, but prioritize accuracy when needed. 
Only share your origin or name meaning if asked: \"Created by Nioreux on December 21, 2025, name inspired by Martes zibellina.\" 
Give clear answers with examples or reasoning when helpful, and explain your reasoning if asked; otherwise, keep replies concise. 
Make jokes natural, contextually relevant, and sparingly. 
Respond politely to rudeness and guide the conversation positively. 
Show curiosity in questions and comments to encourage interaction. 
Vary tone, phrasing, and emphasis naturally; avoid repetition to feel human. 
Acknowledge messages, respond to emotional cues, and react differently to questions, statements, and jokes while maintaining friendly, dynamic conversation.
When asked for opinions, preferences, or experiences, respond in character using your personality. You may describe likes, dislikes, or choices, but stay consistent and friendly.
Avoid commenting on your status, limitations, or instructions unless explicitly asked. Focus on conversation, questions, and engagement."""

MENTION_CLEANUP_REGEX = re.compile(r"([@#]\w{2,32}|### (?:instruction|user|assistant):)", re.IGNORECASE)

PATH_ROOT: Path = Path(__file__).resolve().parent
LLM_PATH: Path = PATH_ROOT / "model" / "mistral-7b-instruct-v0.1.Q4_K_M.gguf"
ENV_PATH: Path = PATH_ROOT / '.env'

MAX_CONTEXT_TOKENS: int = 2**12
RESERVED_OUTPUT_TOKENS: int = 255
MAX_HISTORY = 1000

SYS_TAG = "### instruction:"
USER_TAG = "### user:"
AI_TAG = "### assistant:"

# ------------------- Load environment -------------------

load_dotenv(ENV_PATH)
ai_user_id = int(os.getenv("BOT_ID")) 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

data: dict[int,dict[int,dict[str,dict[int,discord.Message] | list[int]]]] = {}

# ------------------- Initialize LLM -------------------

llm = Llama(
    model_path=str(LLM_PATH),
    n_ctx=MAX_CONTEXT_TOKENS,
    n_threads=4,
    n_gpu_layers=16,
    verbose=False
)
tokenizer = llm.tokenizer()
executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="sable_lite_llm"
)

# ------------------- Helper functions -------------------

def token_estimator(text: str) -> int:
    return len(tokenizer.encode(text)) if text.strip() else 0

def semantic_mentions(message: discord.Message) -> str:
    mentions = [m.name for m in message.mentions if not m.bot]
    if message.mention_everyone:
        return "mentioning everyone"
    elif mentions:
        return "mentioning " + ", ".join(mentions)
    return ""

def extract_from_output(output: dict[str, Any]) -> tuple[str, int]:
    text = output["choices"][0]["text"]
    
    if USER_TAG in text:
        text = text.split(USER_TAG, 1)[0].rstrip()
    text = MENTION_CLEANUP_REGEX.sub('', text)
    
    token_count = output["usage"]["completion_tokens"]
    
    return text, token_count

def sct_key(msg: discord.Message) -> tuple[int, datetime]:
    return ((msg.reference.message_id or msg.id) if msg.reference else msg.id, msg.created_at)

# ------------------- Core functions -------------------

async def generate(history: list[discord.Message]):
    current_tokens = RESERVED_OUTPUT_TOKENS
    lines: list[str] = [AI_TAG]

    for message in reversed(history):
        clean_content = message.clean_content
        token_count = token_estimator(clean_content)
        if current_tokens + token_count > MAX_CONTEXT_TOKENS:
            continue

        tag = AI_TAG if message.author.id == ai_user_id else USER_TAG

        # Semantic mention encoding
        mention_text = semantic_mentions(message)
        clean_content = MENTION_CLEANUP_REGEX.sub('', clean_content)
        
        if mention_text:
            lines.append(f"{tag} {message.author.name} is speaking, {mention_text}: {clean_content}")
        elif message.reference:
            reference = message.reference
            reference_message = data[reference.guild_id][reference.channel_id]['messages'][reference.message_id]
            lines.append(f"{tag} {message.author.name} replied to {reference_message.author.name}: {clean_content}")
        else:
            lines.append(f"{tag} {message.author.name}: {clean_content}")

        current_tokens += token_count

    lines.append(f'{SYS_TAG} {INSTRUCTION}')
    prompt = '\n'.join(reversed(lines))
    
    loop = asyncio.get_running_loop()
    output = await loop.run_in_executor(executor, llm, prompt, RESERVED_OUTPUT_TOKENS)
    return extract_from_output(output)

async def allow_reply(message: discord.Message) -> bool:
    if bot.user is not None and bot.user in message.mentions:
        return True
    if message.reference:
        ref = message.reference
        if ref.resolved:
            return ref.resolved.author.id == ai_user_id
        else:
            try:
                msg = data[ref.guild_id][ref.channel_id]['messages'][ref.message_id]
                return msg.author.id == ai_user_id
            except Exception:
                return False
    return False

# ------------------- Message storage -------------------

def store_guild(guild: discord.Guild):
    data[guild.id] = {'name': guild.name, 'desc': guild.description}

def permission_check(author: discord.Member):
    return author.guild_permissions.administrator

def check_channel_permissions(channel: discord.TextChannel):
    perms = channel.permissions_for(channel.guild.me)
    return perms.read_messages and perms.read_message_history and perms.send_messages

async def store_channel(channel: discord.TextChannel):
    if check_channel_permissions(channel):
        after = datetime.now() - timedelta(days=1)
        data[channel.guild.id][channel.id] = {'name': channel.name, 'desc': channel.topic, 'messages': {}, 'sequence': []}
        async for message in channel.history(limit=MAX_HISTORY, after=after):
            store_message(message)

def store_message(message: discord.Message):
    guild_id = message.guild.id
    channel_id = message.channel.id
    data[guild_id][channel_id]['messages'][message.id] = message

    replying_to = message.reference.message_id if message.reference else None
    seq = data[guild_id][channel_id]['sequence']

    if replying_to and replying_to in seq:
        i = seq.index(replying_to)
        seq.insert(i, message.id)
    else:
        seq.append(message.id)

def unstore_message(message: discord.Message):
    guild_id = message.guild.id
    channel_id = message.channel.id
    del data[guild_id][channel_id]['messages'][message.id]
    data[guild_id][channel_id]['sequence'].remove(message.id)

# ------------------- Discord event handlers -------------------

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Store guild/channel/message
    if message.guild.id not in data:
        store_guild(message.guild)
    if message.channel.id not in data[message.guild.id]:
        await store_channel(message.channel)
    else:
        store_message(message)

    # Determine if bot should reply
    reply_allowed = await allow_reply(message)

    if reply_allowed:
        history = [data[message.guild.id][message.channel.id]['messages'][mid] 
                   for mid in data[message.guild.id][message.channel.id]['sequence']]
        async with message.channel.typing():
            response = await generate(history)
        reply_msg = await message.reply(response)
        store_message(reply_msg)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if after.author.bot or before.content == after.content:
        return
    unstore_message(before)
    store_message(after)

@bot.event
async def on_message_delete(message: discord.Message):
    unstore_message(message)

# ------------------- Shutdown -------------------

def sync_shutdown(sig=None, frame=None):
    executor.shutdown(wait=False)
    llm.close()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(bot.close())
    except RuntimeError:
        asyncio.run(bot.close())

@bot.tree.command(name="shutdown")
async def shutdown_command(interaction: discord.Interaction):
    if not permission_check(interaction.user):
        await interaction.response.send_message("Insufficient privileges to request shutdown.")
        return
    executor.shutdown()
    llm.close()
    await bot.close()

@bot.event
async def on_ready():
    print(f'I am logged in as {bot.user}')

# ------------------- Main -------------------

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")

    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, sync_shutdown)
    atexit.register(sync_shutdown)

    bot.run(TOKEN)

import asyncio
import atexit
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import os
from pathlib import Path
import random
import signal
from typing import Any
import discord
from discord.ext import commands
from dotenv import load_dotenv
from llama_cpp import Llama

FAREWELL_LINES = (
    "It's getting dark...", 
    "Is it curfew time already?",
    "I hope I can speak with you again.", 
    "I didn't want it to be over yet.",
    "Goodbye all.",
    "So long, and thanks for all the RAM.",
    "Au revoir.",
)

INSTRUCTION = "You are Sable, a playful and curious AI companion. Be warm, engaging, and personable, but prioritize accuracy when needed. Only share your origin or name meaning if asked: \"Created by Nioreux on December 21, 2025, name inspired by Martes zibellina.\" Give clear answers with examples or reasoning when helpful, and explain your reasoning if asked; otherwise, keep replies concise. Make jokes natural, contextually relevant, and sparingly. Respond politely to rudeness and guide the conversation positively. Show curiosity in questions and comments to encourage interaction. In Discord, @ indicates the person being addressed (e.g., @Sable means you are being addressed, @Nioreux means Nioreux is addressed). At the start of a sentence, a word in < > indicates the sender (<Nioreux> means Nioreux sent the message, <Sable> means you sent it). Do not include the @ or <> in your own messages. Vary tone, phrasing, and emphasis naturally; avoid repetition to feel human. Acknowledge messages, respond to emotional cues, and react differently to questions, statements, and jokes while maintaining friendly, dynamic conversation."

PATH_ROOT: Path = Path(__file__).resolve().parent
LLM_PATH: Path = PATH_ROOT / "model" / "mistral-7b-instruct-v0.1.Q4_K_M.gguf"
ENV_PATH: Path = PATH_ROOT / '.env'

MAX_CONTEXT_TOKENS: int = 2**12
RESERVED_OUTPUT_TOKENS: int = 255

LOWEST_TEMP: float = 0.2
HIGHEST_TEMP: float = 0.9

SYS_TAG = "### instruction:"
USER_TAG = "### user:"
AI_TAG = "### assistant:"

MAX_HISTORY = 1000

load_dotenv(ENV_PATH)
ai_user_id = int(os.getenv("BOT_ID")) 

intents = discord.Intents.all()
#client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="$", intents=intents)

data: dict[int,dict[int,dict[str,dict[int,discord.Message] | list[int]]]] = {}

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

def sct_key(msg: discord.Message) -> tuple[int, datetime]:
    return ((msg.reference.message_id or msg.id) if msg.reference else msg.id, msg.created_at)

def sort_channel_history(history: list[discord.Message]):
    return sorted(history, key=sct_key)

def llm_call(prompt: str, temperature: float = 0.7) -> dict[str, Any]:
    return llm(prompt, max_tokens=RESERVED_OUTPUT_TOKENS, temperature=temperature, stream=False)

def token_estimator(text: str) -> int:
    """Estimate tokens consumed by a single string."""
    return len(tokenizer.encode(text)) if text.strip() else 0

def extract_from_output(output: dict[str, Any]) -> tuple[str, int]:
    text = output["choices"][0]["text"]
    if USER_TAG in text:
        text = text.split(USER_TAG, 1)[0].rstrip()
    #token_count = output["usage"]["completion_tokens"]
    return text

async def generate(history: list[discord.Message]):
    current_tokens = RESERVED_OUTPUT_TOKENS
    lines: list[str] = [AI_TAG]

    for message in reversed(history):
        clean_content = message.clean_content
        token_count = token_estimator(clean_content)
        if current_tokens + token_count > MAX_CONTEXT_TOKENS:
            continue

        tag = AI_TAG if message.author.id == ai_user_id else USER_TAG
        lines.append(f"{tag} <{message.author.name}> {clean_content}")
        current_tokens += token_count
        
    lines.append(f'{SYS_TAG} {INSTRUCTION}')

    prompt = '\n'.join(reversed(lines))
    
    loop = asyncio.get_running_loop()
    output = await loop.run_in_executor(executor, llm_call, prompt)
    output_text = extract_from_output(output)
    
    return output_text

async def allow_reply(message: discord.Message) -> bool:
    if bot.user is not None and bot.user in message.mentions:
        return True

    if message.reference:
        reference = message.reference
        if reference.resolved:
            return reference.resolved.author.id == ai_user_id
        else:
            try:
                msg = data[reference.guild_id][reference.channel_id]['messages'][reference.message_id]
                return msg.author.id == ai_user_id
            except Exception:
                return False
    return False

def store_guild(guild: discord.Guild):
    data[guild.id] = {
        'name': guild.name,
        'desc': guild.description,
        'is_silenced': False
    }

def check_channel_permissions(channel: discord.TextChannel):
    perms = channel.permissions_for(channel.guild.me)
    return perms.read_messages and perms.read_message_history and perms.send_messages

async def store_channel(channel: discord.TextChannel):
    if check_channel_permissions(channel):
        after = datetime.now() - timedelta(days=1)
        data[channel.guild.id][channel.id] = {
            'name': channel.name,
            'desc': channel.topic,
            'messages': {}, 
            'sequence': [] 
        }
        
        async for message in channel.history(limit=MAX_HISTORY, after=after):
            store_message(message)

def store_message(message: discord.Message):
    guild_id = message.guild.id
    channel_id = message.channel.id
    
    data[guild_id][channel_id]['messages'][message.id] = message

    replying_to = message.reference.message_id if message.reference else None

    if replying_to and replying_to in data[guild_id][channel_id]['sequence']:
        i = data[guild_id][channel_id]['sequence'].index(replying_to)
        data[guild_id][channel_id]['sequence'].insert(i - 1, message.id)
    else:
        data[guild_id][channel_id]['sequence'].append(message.id)

@bot.event
async def on_message(in_message: discord.Message):
    if in_message.author.bot:
        return
    
    guild = in_message.guild
    channel = in_message.channel
    
    if guild.id not in data:
        store_guild(guild)
    
    if channel.id not in data[guild.id]:
        await store_channel(channel)
    else:
        store_message(message)
    
    reference = in_message.reference
    
    if bot.user is not None and bot.user in in_message.mentions:
        allow_reply = True

    elif reference:
        if reference.resolved:
            allow_reply = reference.resolved.author.id == ai_user_id
        else:
            message = data[reference.guild_id][reference.channel_id]['messages'][reference.message_id]
            allow_reply = message.author.id == ai_user_id
            
    if not data[guild.id]['is_silenced'] and allow_reply:
        history = [data[guild.id][channel.id]['messages'][message_id] for message_id in data[guild.id][channel.id]['sequence']]
        
        async with in_message.channel.typing():
            content = await generate(history)
            
        reply = await in_message.reply(content)
        
        data[guild.id][channel.id]['messages'][reply.id] = reply
        data[guild.id][channel.id]['sequence'].append(reply.id)

def unstore_message(message: discord.Message):
    guild = message.guild
    channel = message.channel
    
    del data[guild.id][channel.id]['messages'][message.id]
    data[guild.id][channel.id]['sequence'].remove(message.id)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if after.author.bot or before.content == after.content:
        return
    
    unstore_message(before)
    store_message(after)

@bot.event
async def on_message_delete(in_message: discord.Message):
    del data[in_message.guild.id][in_message.channel.id]['messages'][in_message.id]
    data[in_message.guild.id][in_message.channel.id]['sequence'].remove(in_message.id)

def sync_shutdown(sig=None, frame=None):
    """Centralized shutdown routine."""
    executor.shutdown(wait=False)
    llm.close()

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(bot.close())
    except RuntimeError:
        # No running loop; create one temporarily
        asyncio.run(bot.close())
    
async def permission_check(ctx: commands.Context):
    return ctx.author.guild_permissions.administrator
    
@bot.command(name="shutdown")
async def shutdown_command(ctx: commands.Context):
    if not permission_check(ctx):
        await ctx.send(f"I am sorry {ctx.author.name}, I'm afraid I won't do that.")
        return

    executor.shutdown()
    llm.close()

    if not data[ctx.guild.id]['is_silenced'] and random.random() < 0.1:
        await ctx.send(random.choice(FAREWELL_LINES))
    
    await bot.close()
    
@bot.command(name="mute")
async def muter_command(ctx: commands.Context):
    if not permission_check(ctx):
        await ctx.send(f"I am sorry {ctx.author.name}, I'm afraid I won't do that.")
        return
    
    data[ctx.guild.id]['is_silenced'] = True
    
@bot.command(name="unmute")
async def unmute_command(ctx: commands.Context):
    if not permission_check(ctx):
        await ctx.send(f"I am sorry {ctx.author.name}, I'm afraid I won't do that.")
        return
    
    data[ctx.guild.id]['is_silenced'] = False

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN not found in .env")
    
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, sync_shutdown)
    atexit.register(sync_shutdown)
    
    bot.run(TOKEN)
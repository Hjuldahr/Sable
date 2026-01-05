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

INSTRUCTION = "You are Sable, a playful and curious AI companion. Be warm, engaging, and personable, but prioritize accuracy when needed. Only share your origin or name meaning if asked: \"Created by Nioreux on December 21, 2025, name inspired by Martes zibellina.\" Give clear answers with examples or reasoning when helpful, and explain your reasoning if asked; otherwise, keep replies concise. Make jokes natural, contextually relevant, and sparingly. Respond politely to rudeness and guide the conversation positively. Show curiosity in questions and comments to encourage interaction. In Discord, @ indicates the person being addressed (e.g., @Sable means you are being addressed, @Nioreux means Nioreux is addressed). At the start of a sentence, a word in < > indicates the sender (<Nioreux> means Nioreux sent the message, <Sable> means you sent it). Vary tone, phrasing, and emphasis naturally; avoid repetition to feel human. Acknowledge messages, respond to emotional cues, and react differently to questions, statements, and jokes while maintaining friendly, dynamic conversation."

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

@bot.event
async def on_message(in_message: discord.Message):
    if in_message.author.bot:
        return
    
    guild_id = in_message.guild.id
    channel_id = in_message.channel.id
    in_message_id = in_message.id
    
    if guild_id not in data:
        data[guild_id] = {
            'is_silenced': False
        }
    
    if channel_id not in data[guild_id]:
        data[guild_id][channel_id] = {
            'messages': {in_message_id: in_message}, 
            'sequence': [] 
        }
    
    else:
        data[guild_id][channel_id]['messages'][in_message_id] = in_message
        
        reference_id = in_message.reference.message_id if in_message.reference else None
        
        if reference_id and reference_id in data[guild_id][channel_id]['sequence']:
            i = data[guild_id][channel_id]['sequence'].index(reference_id)
            data[guild_id][channel_id]['sequence'].insert(max(i - 1, 0), in_message_id)
        else:
            data[guild_id][channel_id]['sequence'].append(in_message_id)
    
    reference = in_message.reference
    
    if bot.user is not None and bot.user in in_message.mentions:
        allow_reply = True

    elif reference:
        if reference.resolved:
            allow_reply = reference.resolved.author.id == ai_user_id
        else:
            message = data[reference.guild_id][reference.channel_id]['messages'][reference.message_id]
            allow_reply = message.author.id == ai_user_id
            
    if not data[guild_id]['is_silenced'] and allow_reply:
        history = [data[guild_id][channel_id]['messages'][message_id] for message_id in data[guild_id][channel_id]['sequence']]
        
        async with in_message.channel.typing():
            content = await generate(history)
            
        reply = await in_message.reply(content)
        
        data[guild_id][channel_id]['messages'][reply.id] = reply
        data[guild_id][channel_id]['sequence'].append(reply.id)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    guild_id = after.guild.id
    before_channel_id = before.channel.id
    after_channel_id = after.channel.id
    
    if after.author.bot or before.content == after.content:
        return
    
    if before.channel != after.channel:
        del data[before_channel_id]['messages'][before.id]
        data[guild_id][before_channel_id]['sequence'].remove(before.id)
        
        data[guild_id][after_channel_id]['messages'][after.id]
        
        replying_to = after.reference.message_id if after.reference else None
        
        if replying_to and replying_to in data[after_channel_id]['sequence']:
            i = data[guild_id][after_channel_id]['sequence'].index(replying_to)
            data[guild_id][after_channel_id]['sequence'].insert(i - 1, after.id)
        else:
            data[guild_id][after_channel_id]['sequence'].append(after.id)

@bot.event
async def on_message_delete(in_message: discord.Message):
    del data[in_message.guild.id][in_message.channel.id]['messages'][in_message.id]
    data[in_message.guild.id][in_message.channel.id]['sequence'].remove(in_message.id)
    
@bot.event
async def on_ready():
    after = datetime.now() - timedelta(days=1)
    
    for guild in bot.guilds:
        guild_id = guild.id
        data[guild_id] = {'is_silenced': False}
        me = guild.me
        
        for channel in guild.text_channels:
            channel_id = channel.id
            perms = channel.permissions_for(me)
            
            if perms.read_messages and perms.read_message_history and perms.send_messages:
                data[guild_id][channel_id] = { 'messages': {}, 'sequence': [] }
                
                async for message in channel.history(limit=MAX_HISTORY, after=after):
                    if channel_id not in data:
                        data[guild_id][channel_id]['messages'][message.id] = message
                        
                        replying_to = message.reference.message_id if message.reference else None
                        
                        if replying_to and replying_to in data[guild_id][channel_id]['sequence']:
                            i = data[guild_id][channel_id]['sequence'].index(replying_to)
                            data[guild_id][channel_id]['sequence'].insert(i - 1, message.id)
                        else:
                            data[guild_id][channel_id]['sequence'].append(message.id)

async def safe_shutdown():
    """Centralized shutdown routine."""
    executor.shutdown(wait=False)
    llm.close()
    await bot.close()
    
async def permission_check(ctx):
    return ctx.author.guild_permissions.administrator
    
@bot.command(name="shutdown")
async def shutdown_command(ctx: commands.Context):
    if not permission_check(ctx):
        await ctx.send(f"I am sorry {ctx.author.name}, I'm afraid I won't do that.")
        return

    if not data[ctx.guild.id]['is_silenced'] and random.random() < 0.1:
        await ctx.send(random.choice(FAREWELL_LINES))
        
    await safe_shutdown()

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
        signal.signal(s, safe_shutdown)
    atexit.register(safe_shutdown)
    
    bot.run(TOKEN)
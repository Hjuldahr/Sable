import asyncio
import atexit
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import io
import os
from pathlib import Path
import re
import signal
from typing import Any, Optional
import discord
from discord.ext import commands
from dotenv import load_dotenv
from llama_cpp import Llama

class UserAudioSink(discord.sinks.Sink):
    def __init__(self):
        super().__init__()
        self.buffers = defaultdict(io.BytesIO)

    def write(self, data, user):
        if user.bot:
            return
        #discord.opus.Decoder
        self.buffers[user.id].write(data)

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

def extract_from_output(output: dict[str, Any]) -> tuple[str, int]:
    text = output["choices"][0]["text"]
    
    if USER_TAG in text:
        text = text.split(USER_TAG, 1)[0].rstrip()
    text = MENTION_CLEANUP_REGEX.sub('', text)
    
    token_count = output["usage"]["completion_tokens"]
    
    return text, token_count

def sct_key(msg: discord.Message) -> tuple[int, datetime]:
    return ((msg.reference.message_id or msg.id) if msg.reference else msg.id, msg.created_at)

@bot.command()
@commands.is_owner()
async def sync(ctx):
    """push your local slash commands to Discord's servers""" 
    await bot.tree.sync()
    await ctx.send("Synced commands")

@bot.command()
async def sync_guild(ctx: commands.Context):
    # Sync to a specific guild (instant for testing)
    await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"Synced commands to guild {ctx.guild.id}! (press CTRL+R to refresh your session)")

# ------------------- Core functions -------------------

def permission_check(author: discord.Member):
    return author.guild_permissions.administrator

# ------------------- Voice Messaging -------------------

async def recording_finished(sink: UserAudioSink, vc: discord.VoiceClient):
    print(f"Finished recording in channel {vc.channel.name}")

async def voice_recording_task(vc: discord.VoiceClient):
    sink = UserAudioSink()
    vc.start_recording(sink, recording_finished, vc)
    
    try:
        while vc.is_connected():
            # Process live audio here if you want, e.g., read per-user streams
            for user_id, stream in sink.buffers.items():
                stream.seek(0)
                chunk = stream.read()
                if chunk:
                    # Feed chunk into your AI or processing function
                    pass
                stream.seek(0, io.SEEK_END)  # reset to append new audio
            await asyncio.sleep(0.5)  # adjustable polling interval
    finally:
        if vc.is_recording():
            vc.stop_recording()

@bot.tree.command(name="join", description="Request Sable to join a guild voice channel")
async def join(interaction: discord.Interaction, voice_channel: Optional[discord.VoiceChannel] = None):
    # Determine which channel to join
    target_channel = voice_channel or (interaction.user.voice.channel if interaction.user.voice else None)

    if not target_channel:
        return await interaction.response.send_message(
            "You must be in a voice channel or specify one!", ephemeral=True
        )

    voice_client = interaction.guild.voice_client

    if voice_client:
        # If already in the target channel, do nothing
        if voice_client.channel.id == target_channel.id:
            return await interaction.response.send_message(
                f"I'm already in {target_channel.name}!", ephemeral=True
            )
        # Move to the new channel instead of disconnecting/reconnecting
        await voice_client.move_to(target_channel)
    else:
        # Connect for the first time
        await target_channel.connect()

    await interaction.response.send_message(f"Joined **{target_channel.name}**", ephemeral=True)

@bot.tree.command(name="leave", description="Request Sable to leave from voice")
async def leave(itx: discord.Interaction):
    voice_client = itx.guild.voice_client  
    
    if voice_client:
        await voice_client.disconnect()
        await itx.response.send_message("Disconnected from the voice channel.", ephemeral=True)
    else:
        await itx.response.send_message("I am not currently in a voice channel.", ephemeral=True)

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
async def shutdown_command(itx: discord.Interaction):
    if not permission_check(itx.user):
        await itx.response.send_message("Insufficient privileges to request shutdown.", ephemeral=True)
        return
    await itx.response.send_message(
        "Command received. I will begin clean up and shut down.", ephemeral=True
    )
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

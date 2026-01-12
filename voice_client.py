import asyncio
import atexit
import audioop
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import discord
from discord.ext import commands
from dotenv import load_dotenv
import io
from llama_cpp import Llama
import os
from pathlib import Path
import re
import signal
from typing import Any, Optional
import vosk

class UserAudioSink(discord.sinks.Sink):
    def __init__(self):
        super().__init__()
        self.buffers = defaultdict(io.BytesIO)
        self.recognizers = defaultdict(make_recognizer)

    def write(self, data: bytes, user: discord.User):
        if user.bot:
            return

        # data is 48kHz, 16-bit, stereo PCM
        # Convert to mono
        mono = audioop.tomono(data, 2, 1, 1)

        # Resample 48kHz -> 16kHz
        mono_16k, _ = audioop.ratecv(
            mono,          # input
            2,             # sample width (16-bit)
            1,             # channels
            48000,         # input rate
            16000,         # output rate
            None
        )

        self.buffers[user.id].write(mono_16k)
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
LLM_PATH: Path = PATH_ROOT / "model" / "mistral-7b-instruct" / "mistral-7b-instruct-v0.1.Q4_K_M.gguf"
VOSK_PATH: Path = PATH_ROOT / "model" / "vosk-model-small-en-us-0.15"
ENV_PATH: Path = PATH_ROOT / '.env'

MAX_CONTEXT_TOKENS: int = 2**12
RESERVED_OUTPUT_TOKENS: int = 255
MAX_HISTORY = 1000

SYS_TAG = "### instruction:"
USER_TAG = "### user:"
AI_TAG = "### assistant:"

VOSK_SAMPLERATE = 16000
VOSK_MODEL = vosk.Model(VOSK_PATH)
REC = vosk.KaldiRecognizer(VOSK_MODEL, VOSK_SAMPLERATE)

# ------------------- Load environment -------------------

load_dotenv(ENV_PATH)
ai_user_id = int(os.getenv("BOT_ID")) 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

data: dict[int,dict[int,dict[str,dict[int,discord.Message] | list[int]]]] = {}

# ------------------- Initialize LLM -------------------

LLM = Llama(
    model_path=str(LLM_PATH),
    n_ctx=MAX_CONTEXT_TOKENS,
    n_threads=4,
    n_gpu_layers=16,
    verbose=False
)
tokenizer = LLM.tokenizer()
executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="sable_lite_LLM"
)

# ------------------- Helper functions -------------------

def make_recognizer():
    return vosk.KaldiRecognizer(VOSK_MODEL, VOSK_SAMPLERATE)

async def recording_finished(sink: UserAudioSink, vc: discord.VoiceClient):
    print(f"[voice] recording finished in {vc.channel}")

def token_estimator(text: str) -> int:
    return len(tokenizer.encode(text)) if text.strip() else 0

def extract_from_output(output: dict[str, Any]) -> tuple[str, int]:
    text = output["choices"][0]["text"]
    
    if USER_TAG in text:
        text = text.split(USER_TAG, 1)[0].rstrip()
    
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

def create_prompt(transcript: list[dict[str,Any]]) -> str:
    current_tokens = RESERVED_OUTPUT_TOKENS
    lines: list[str] = [AI_TAG]

    for message in reversed(transcript):
        clean_content = message.clean_content
        token_count = token_estimator(clean_content)
        if current_tokens + token_count > MAX_CONTEXT_TOKENS:
            continue

        tag = AI_TAG if message['is_sable'] else USER_TAG
        lines.append(f"{tag} {message.author.name}: {clean_content}")
        current_tokens += token_count

    lines.append(f'{SYS_TAG} {INSTRUCTION}')
    prompt = '\n'.join(reversed(lines))
    
    return prompt

async def stream_output(prompt: str):
    for output in LLM(prompt, suffix='M', stream=True, stop=(USER_TAG,AI_TAG), stopping_criteria="repetition_penalty"):
        yield output["choices"][0]["text"]

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
            for user_id, stream in sink.buffers.items():
                stream.seek(0)
                data = stream.read()
                stream.truncate(0)
                stream.seek(0)

                if not data:
                    continue

                rec = sink.recognizers[user_id]

                if rec.AcceptWaveform(data):
                    result = rec.Result()
                    print(f"[speech][{user_id}] {result}")
                    # TODO accumalate window of words until end of conversation
                    # TODO prompt AI if Sable is mentioned by name
                else:
                    partial = rec.PartialResult()
                    # optional: handle partials

            await asyncio.sleep(0.25)

    finally:
        if vc.is_recording():
            vc.stop_recording()

@bot.tree.command(name="join")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message(
            "You must be in a voice channel.", ephemeral=True
        )

    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    if vc:
        await vc.move_to(channel)
    else:
        vc = await channel.connect()

    bot.loop.create_task(voice_recording_task(vc))
    await interaction.response.send_message(
        f"Joined **{channel.name}** and listening.", ephemeral=True
    )

@bot.tree.command(name="leave")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message(
            "Disconnected and stopped listening.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "I'm not in a voice channel.", ephemeral=True
        )

# ------------------- Shutdown -------------------

def sync_shutdown(sig=None, frame=None):
    executor.shutdown(wait=False)
    LLM.close()
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
    LLM.close()
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

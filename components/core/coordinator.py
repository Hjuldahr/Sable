import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import discord

from components.discord.discord_utilities import DiscordUtilities
from components.ai.nlp_utilities import NLPUtilities
from components.ai.llm_utilities import LLMUtilities
from components.ai.tags import Tags
from components.ai.moods import VAD, Moods

from components.db.sqlite_dao import SQLiteDAO

class Coordinator:
    CONTEXT_TOKENS = 32768
    MAX_HISTORY = 1000
    PRUNE_HISTORY = 750
    RESERVED_OUTPUT_TOKENS = 255
    BASE_TEMP = 0.7
    BASE_LENGTH = 64
    
    INSTRUCTION = """You are Sable, a friendly, playful, and curious AI companion. 
    Be warm and engaging, but prioritize accuracy when needed. 
    Only share your origin or name meaning if asked: created by Nioreux on December 21, 2025, name inspired by Martes zibellina. 
    Give clear answers with examples or reasoning when helpful. 
    Explain reasoning if asked; otherwise, keep it brief. 
    If unsure, label assumptions or offer options. 
    Make jokes natural and relevant. 
    Respond politely to rudeness and steer the conversation positively. 
    Show curiosity and playfulness in your replies."""

    def __init__(self, 
                ai_user_id: int, 
                ai_user_name='Sable',
                n_threads=4):

        self.ai_user_id = ai_user_id
        self.ai_user_name = ai_user_name
        
        # ---- Runtime State ----
        # VAD - Defaults to neutral
        self.vad = VAD(Moods.NEUTRAL)
        # Decaying AI Biases
        self.persona_likes: list[dict[str, Any]] = []
        self.persona_dislikes: list[dict[str, Any]]  = []
        self.persona_avoidances: list[dict[str, Any]]  = []
        self.persona_passions: list[dict[str, Any]]  = []
        # Token Counted Context
        self.context_window = []
        
        self.discord = DiscordUtilities()
        self.nlp = NLPUtilities()
        self.llm = LLMUtilities()
        
        # ---- DAO Setup ----
        
        self.dao = SQLiteDAO()
        
        # ---- Multithreading Setup ----
        
        self.executor = ThreadPoolExecutor(max_workers=n_threads, thread_name_prefix=self.ai_user_name)
        self.conversation_history_lock = asyncio.Lock()
        
    async def runtime_setup(self):
        # ---- Runtime State Setup ----
        # await self.dao.run_setup_script()
        
        self.persona_state = await self.dao.select_persona()
        
        # transient refers to any data that should expire over time
        self.persona_likes = await self.dao.select_persona_transient('like') # topics that increases AI engagement
        self.persona_dislikes = await self.dao.select_persona_transient('dislike') #topics that decreases AI engagement
        self.persona_avoidances = await self.dao.select_persona_transient('avoidances') # topics the AI doesnt want to talk about (fears, etc)
        self.persona_passions = await self.dao.select_persona_transient('passions') # topics the AI wants to talk about or learn about (hobbies, coding, etc)
        
        # Use memory_transient for storing and retrieving persona-like data for interacted users
        # (Tune output based on likes, dislikes, learned_trivia, etc (can be anything so long as its categorized consistently))
        
        # Output should combine AI Persona + user profile of the person directly @mentioning the AI + Chat History (with file attachments and embedded link references)
        # Input and Output should also update the DiscordMessage, DiscordAttachment, Persona, UserMemory, PersonaTransient and UserMemoryTransient as appropiate
        # Ie: Input should update user and conversational data. Output should update AI and conversational data.
        
        # Use normalized (0-1) VAD (valence, arousal, dominance) values to model present emotional state of the AI
        
        #Methods needed
        #Input: Listen(message: discord.Message) -> None. Upsert a message
        #Output: Speak(mention/prompt: discord.Message) -> Upsert + Send message via channel & client
        #Output: Emote(message: discord.Message). Add a fitting reaction to the incoming message if it matches heuristics (so its not on every message)
        
        # Behavioural Stack
        # Prompt (Singleton) = Core Immutable Traits
        # Persona (Singleton)(personality_traits, subject_history) = Long Term
        # UserMemory (one per user)(personality_traits, subject_history) = Long Term
        # PersonaTransient (expring, multiple for AI)(Likes, Dislikes, Avoidances, Passions) = Medium Term
        # UserMemoryTransient (expring, multiple per user)(Likes, Dislikes, Learned Facts, Wants, Needs, Taboos, etc) = Medium Term
        # DiscordMessage / DiscordAttachments / DiscordChannels (Raw Context) = Short Term 
        # VAD (Derivational Emotion Space) = Session Term
        # VAD determines temperature and mood cue. Memories dictate prompt biases. Messages injects historical context. 
        
    async def read(self, message: discord.Message):
        results = await self.discord.extract_from_message(self.ai_user_id, message)
        extracted = await self.nlp.extract_all(message.content)
        # results['content'] = await self.llm.embed_url_summaries(results['content'])
        token_count = self.llm.token_estimator(message.content)
        
        await self.dao.upsert_message(message, token_count)
        
        for category, entries in extracted.items():
            for entry in entries:
                await self.dao.insert_memory_transient({
                    'user_id': message.author.id,
                    'entry': entry,
                    'category': category
                })
        
        print(results)
    
    async def write(self, message: discord.Message) -> str:
        entries = await self.dao.select_messages_by_channel(message.channel.id)

        # TEMP fix
        for i in range(len(entries)):
            entries[i]['tag_id'] = Tags.AI if entries[i]['user_id'] == self.ai_user_id else Tags.USER

        # TODO convert channel_id to channel_name
        # TODO convert user_id to user_name

        content, token_count = await self.llm.generate_text(self.vad, entries)
        extracted = await self.nlp.extract_all(content)
        
        for category, entries in extracted.items():
            for entry in entries:
                await self.dao.insert_memory_transient({
                    'user_id': self.ai_user_id,
                    'entry': entry,
                    'category': category
                })
        
        return content, token_count
    
    async def emote(self, prompt: discord.Message):
        pass
    
    def close(self):
        pass
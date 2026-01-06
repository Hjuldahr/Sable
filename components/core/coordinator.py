import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random
from typing import Any
import discord

from components.ai.nlp_utilities import NLPUtilities
from components.ai.llm_utilities import LLMUtilities
from components.ai.moods import VAD, Moods, VADWords
from components.db.sqlite_dao import SQLiteDAO
from components.discord.discord_utilities import DiscordUtilities
from components.discord.reactions import ReactionSelector

from .context import ContextBuilder


# self.persona_likes = await self.dao.select_persona_transient('like') # topics that increases AI engagement
# self.persona_dislikes = await self.dao.select_persona_transient('dislike') #topics that decreases AI engagement
# self.persona_avoidances = await self.dao.select_persona_transient('avoidances') # topics the AI doesnt want to talk about (fears, etc)
# self.persona_passions = await self.dao.select_persona_transient('passions') # topics the AI wants to talk about or learn about (hobbies, coding, etc)

# transient refers to any data that should expire over time

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

class Coordinator:
    def __init__(self, ai_user_id: int, ai_user_name='Sable', n_threads=4):
        VADWords.load()

        self.ai_user_id = ai_user_id
        self.ai_user_name = ai_user_name
        
        # ---- Runtime State ----
        self.vad = VAD(Moods.NEUTRAL)
        
        # ---- Components ----
        self.discord = DiscordUtilities()
        self.nlp = NLPUtilities()
        self.llm = LLMUtilities()
        self.context_builder = ContextBuilder(ai_user_id)
        self.reactions = ReactionSelector()
        
        # ---- DAO Setup ----
        
        self.dao: SQLiteDAO = None
        
    async def async_init(self):
        # ---- Runtime State Setup ----
        self.dao = await SQLiteDAO.create()
        self.persona_state = await self.dao.select_persona()
        
    async def read(self, message: discord.Message): 
        results = await self.discord.extract_from_message(self.ai_user_id, message) 
        extracted = await self.nlp.extract_all(message.content) 
        # is too slow with my current hardware so its currently disabled from use 
        # results['content'] = await self.llm.embed_url_summaries(results['content']) 
        
        token_count = self.llm.token_estimator(message.content) 
        await self.dao.upsert_message(message, token_count) 
        
        # replace with execute many if the repeated connections becomes an issue
        for category, entries in extracted.items(): 
            for entry in entries: 
                await self.dao.insert_memory_transient({'user_id': message.author.id, 'entry': entry, 'category': category}) 
    
    async def write(self, message):
        entries = await self.dao.select_messages_by_channel(message.channel.id)

        user_memory = await self.dao.select_memory_transient_category_grouped(
            message.author.id
        )

        context = self.context_builder.build(
            entries,
            user_memory,
            message.channel.name
        )

        persona = await self.dao.select_persona_transient_all()

        message_vad = VADWords.score(message.content)
        temp_vad = VAD(*self.vad)
        temp_vad.merge(message_vad, 0.2)

        content, token_count = await self.llm.generate_text(
            temp_vad, context, persona, user_memory
        )

        self.update_vad_from_message(content, message_vad)

        return content, token_count
    
    def update_vad_from_message(self, text: str, message_vad: VAD):
        output_vad = VADWords.score(text)
        self.vad.decay()
        self.vad.double_merge(
            message_vad, 0.125,
            output_vad, 0.25
        )
        self.vad.pertubate()
        
    async def emote(self, message: discord.Message):
        transient_persona = await self.dao.select_persona_transient_all()
        emoji = self.reactions.select_reaction(self.vad, transient_persona, message)
        if emoji:
            await message.add_reaction(emoji)
        
    def close(self):
        print("Coordinator Shutting down")
        self.nlp.close()
        self.llm.close()
        print("Coordinator Shutdown")
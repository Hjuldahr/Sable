from discord import Message, Bot

from .db.database import DatabaseManager
from .ai.llm import LargeLanguageModel
from .ai.nlp import NaturalLanguageProcessor
from .ai.moods import VAD, VADTags, VADWords

class Sable:
    USERNAME = 'Sable'

    def __init__(self, discord_user_id: int):
        self.discord_user_id = discord_user_id
        
        self.llm = LargeLanguageModel()
        self.nlp = NaturalLanguageProcessor(4)
        self.vad = VAD(tag=VADTags.NEUTRAL)
        self.dbm = DatabaseManager()
        
        self.persona = None

    async def async_init(self):
        await self.dbManager.async_init() 
        self.persona = await self.dbManager.select_ai_profile()   

    async def async_close(self):
        self.llm.close()
        await self.dbManager.async_close()    

    async def read(self, message: Message):
        extracted = await self.nlp.extract_all(message.content)   

        user_id = message.author.id
        # flatten list to feed into DB (bulk insert more efficient than repeated insert queries)
        values = [
            {'user_id': user_id, 'category': category, 'entry': entry} 
            for category, entries in extracted.items() 
            for entry in entries
        ]
        await self.dbm.insert_user_memories(values)

    async def reply(self, messages: list[Message]) -> str:
        message_vad = VADWords.score(messages[-1].clean_content)
        temp_vad = VAD(*self.vad)
        temp_vad.merge(message_vad, 0.2)

        prompt = await self.llm.async_assemble_prompt_str(messages, temp_vad)
        reply = await self.llm.async_generate(prompt, temp_vad)
        
        extracted = await self.nlp.extract_all(reply) 
        values = [
            {'category': category, 'entry': entry} 
            for category, entries in extracted.items() 
            for entry in entries
        ]
        await self.dbm.insert_ai_memories(values) 
        
        self.update_vad_from_message(reply, message_vad)
        
        return reply    

    def update_vad_from_message(self, text: str, message_vad: VAD):
        output_vad = VADWords.score(text)
        self.vad.decay()
        self.vad.double_merge(
            message_vad, 0.125,
            output_vad, 0.25
        )
        self.vad.pertubate()
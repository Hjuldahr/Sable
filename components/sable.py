from discord import Message

from .db.database import DatabaseManager
from .ai.llm import LLM
from .ai.moods import VAD, VADTags, VADWords

class Sable:
    USERNAME = 'Sable'
    
    def __init__(self):
        self.llm = LLM()
        self.vad = VAD(tag=VADTags.NEUTRAL)
        self.dbManager = DatabaseManager()
        
        self.persona = None
        
    async def async_init(self):
        await self.dbManager.async_init() 
        self.persona = await self.dbManager.select_ai_profile()   
        
    async def async_close(self):
        self.llm.close()
        await self.dbManager.async_close()    
        
    async def reply(self, messages: list[Message]) -> str:
        message_vad = VADWords.score(messages[-1].clean_content)
        temp_vad = VAD(*self.vad)
        temp_vad.merge(message_vad, 0.2)

        prompt = await self.llm.async_assemble_prompt_str(messages, temp_vad)
        reply = await self.llm.async_generate(prompt, temp_vad)
        
        # Extract likes and dislikes
        
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
from discord import Message
from components.llm import LLM

class Sable:
    USERNAME = 'Sable'
    
    def __init__(self):
        self.llm = LLM()
        
    async def reply(self, messages: list[Message]) -> str:
        # TODO re-add VAD emotion loopback

        prompt = await self.llm.async_assemble_prompt_str(messages)
        reply = await self.llm.async_generate(prompt)
        return reply    
        
    def close(self):
        self.llm.close()
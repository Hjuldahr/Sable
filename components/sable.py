from discord import Message
from components.llm import LLM
from components.moods import VAD, VADTags, VADWords

class Sable:
    USERNAME = 'Sable'
    
    def __init__(self):
        self.llm = LLM()
        
        self.vad = VAD(tag=VADTags.NEUTRAL)
        
    async def reply(self, messages: list[Message]) -> str:
        # TODO re-add VAD emotion loopback

        message_vad = VADWords.score(messages[-1].clean_content)
        temp_vad = VAD(*self.vad)
        temp_vad.merge(message_vad, 0.2)

        prompt = await self.llm.async_assemble_prompt_str(messages, temp_vad)
        reply = await self.llm.async_generate(prompt, temp_vad)
        
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
        
    def close(self):
        self.llm.close()
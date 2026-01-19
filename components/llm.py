import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator
from discord import Message
from llama_cpp import CreateCompletionStreamResponse, Llama, LlamaTokenizer
from loguru import logger

from components.moods import VAD, Moods

class LLM:
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
    
    PATH_ROOT: Path = Path(__file__).resolve().parents[2]
    LLM_PATH: Path = PATH_ROOT / "model" / "mistral-7b-instruct-v0.1.Q4_K_M.gguf"
    
    SYS_TAG = "### instruction:"
    USER_TAG = "### user:"
    AI_TAG = "### assistant:"
    END_OF_STREAM_TAG = "<>"
    TAGS = (SYS_TAG,USER_TAG,AI_TAG)
    MAX_TOKENS = 255

    def __init__(self, n_threads = 4, n_gpu_layers = 8):
        self.llm: Llama = Llama(
            model_path=str(self.LLM_PATH),
            n_ctx=self.MAX_CONTEXT_TOKENS,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
            verbose=False
        )
        
        self.tokenizer: LlamaTokenizer = self.llm.tokenizer()
        
        self.executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=n_threads,
            thread_name_prefix="sable_llm"
        )
        
    @staticmethod
    def extract_from_output(output: CreateCompletionStreamResponse) -> str:
        try:
            return output["choices"][0]["text"]
        except KeyError | IndexError as e:
            logger.error('Failed to extract from output', e)
            return ""
    
    async def streaming_generate(self, prompt: str, vad: VAD) -> AsyncGenerator[str, None]:
        temperature = self.remap(vad.arousal, VAD.LOW, VAD.HIGH, self.LOWEST_TEMP, self.HIGHEST_TEMP)
        
        stream = self.llm(
            prompt=prompt,
            suffix=self.END_OF_STREAM_TAG,
            max_tokens=self.MAX_TOKENS,
            temperature=temperature
            stop=self.TAGS,
            stopping_criteria="repeat_penalty",
            stream=True
        )
        for frag in stream:
            yield self.extract_from_output(frag)
    
    def sync_generate(self, prompt: str, vad: VAD) -> str:
        temperature = self.remap(vad.arousal, VAD.LOW, VAD.HIGH, self.LOWEST_TEMP, self.HIGHEST_TEMP)
        
        output = self.llm(
            prompt=prompt,
            max_tokens=self.MAX_TOKENS,
            temperature=temperature
            stop=self.TAGS,
            stopping_criteria="repeat_penalty",
            stream=False
        )
        
        return self.extract_from_output(output)
    
    async def async_generate(self, prompt: str, vad: VAD) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.sync_generate, prompt, vad)
        
    def count_tokens(self, text: str) -> int:
        """Estimate tokens consumed by a single string."""
        return len(self.tokenizer.encode(text)) if text and not text.isspace() else 0
        
    def assemble_instruction_prompt_str(self, vad: VAD) -> str:
        top_moods = [m[0] for m in Moods.label_top_n_moods(vad, 3)]
        mood_line = f"- Your current mood should be: {', '.join(Moods.ordinals(top_moods))}"
        
        return "\n".join((self.INSTRUCTION, mood_line))
        
    def sync_assemble_prompt_str(self, messages: list[Message], vad: VAD) -> str:
        current_tokens = self.RESERVED_OUTPUT_TOKENS    
        lines = deque()
        # Body
        for message in reversed(messages):
            text = message.clean_content
            token_count = self.count_tokens(text)
            # Stop adding older messages when token limit is exceeded
            if current_tokens + token_count > self.MAX_CONTEXT_TOKENS:
                break
            current_tokens += token_count
            lines.appendleft(text)
            
        # Header
        lines.appendleft(self.assemble_instruction_prompt_str(vad))
        # Trailer
        lines.append(self.AI_TAG)
        
        return "\n".join(lines) 
    
    async def async_assemble_prompt_str(self, messages: list[Message], vad: VAD) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.sync_assemble_prompt_str, messages, vad)
    
    def __del__(self):
        self.executor.shutdown(wait=False)
        
    def close(self):
        self.executor.shutdown()
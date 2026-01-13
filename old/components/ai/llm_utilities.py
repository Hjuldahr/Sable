import asyncio
import atexit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
from typing import Any, Iterable, Dict, Tuple, List

import discord
from urlextract import URLExtract
from llama_cpp import Llama
from markitdown import MarkItDown

from .moods import VAD, Moods
from .tags import Tags
from ..discord.reactions import ReactionSelector

class LLMUtilities:
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

    MAX_CONTEXT_TOKENS: int = 2**12
    RESERVED_OUTPUT_TOKENS: int = 255

    LOWEST_TEMP: float = 0.2
    HIGHEST_TEMP: float = 0.9

    NORM_TEXT_REGEX: Tuple[Tuple[re.Pattern, str], ...] = (
        (re.compile(r'(<br\s*/?>|&nbsp;)', re.I), ' '),
        (re.compile(r'[\r\n]+'), ' '),
        (re.compile(r'[^\x20-\x7E]'), ''),
        (re.compile(r'\s+'), ' ')
    )
    MENTION_CLEANUP_REGEX = re.compile(r"([@<]\w{2,32}>?)", re.IGNORECASE)
    
    STOP_CRITERIA = "repetition_penalty"

    def __init__(self, n_threads: int = 2, n_gpu_layers: int = 16):
        self.llm: Llama = Llama(
            model_path=str(self.LLM_PATH),
            n_ctx=self.MAX_CONTEXT_TOKENS,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,
            verbose=False
        )

        self.tokenizer = self.llm.tokenizer()
        self.executor = ThreadPoolExecutor(
            max_workers=n_threads,
            thread_name_prefix="sable_llm"
        )

        self.url_extractor = URLExtract()
        self.reaction_selector = ReactionSelector()

    def close(self) -> None:
        self.executor.shutdown()
        self.llm.close()

    # ---------- Token estimation ----------

    def token_estimator(self, text: str) -> int:
        """Estimate tokens consumed by a single string."""
        return len(self.tokenizer.encode(text)) if text.strip() else 0

    # ---------- Prompt builders ----------

    @classmethod
    def build_context_prompt(cls, entries: Iterable[dict[str, Any]]) -> str:
        """
        Build a prompt context for the LLM from message entries.
        Each entry can include:
            - tag_id: AI or USER
            - user_name: display name
            - content: cleaned message text
            - token_count: estimated tokens for this entry
            - semantic_mentions: optional collapsed mention string
            - reference_info: optional dict with 'ref_user_name' and 'ref_content'
        """
        current_tokens = cls.RESERVED_OUTPUT_TOKENS
        lines: List[str] = []

        # Process messages in reverse so the latest is last in prompt
        for entry in reversed(entries):
            token_count = entry.get("token_count", 0)
            if current_tokens + token_count > cls.MAX_CONTEXT_TOKENS:
                # Stop adding older messages when token limit is exceeded
                break

            tag = Tags.ordinal(entry.get("tag_id", Tags.USER))
            user_name = entry.get("user_name", "Unknown")
            content = entry.get("content", "").strip()

            # Start building the line
            line = f"{tag} {user_name}"

            # Add semantic mentions if present
            semantic_mentions = entry.get("semantic_mentions", "")
            if semantic_mentions:
                line += f", {semantic_mentions}"

            # Add reference info if present
            reference_info = entry.get("reference_info")
            if reference_info:
                ref_user = reference_info.get("ref_user_name", "Unknown")
                ref_content = reference_info.get("ref_content", "")
                if ref_content:
                    # Optionally truncate long reference content for token safety
                    ref_content_trunc = ref_content[:150].replace("\n", " ").strip()
                    line += f" replying to {ref_user}: {ref_content_trunc}"

            # Add the main message content
            line += f": {content}"

            lines.append(line)
            current_tokens += token_count

        # Reverse again so the oldest messages come first in the prompt
        return "\n".join(reversed(lines))

    @classmethod
    def build_instruction_prompt(
        cls,
        vad: VAD,
        persona_transient: dict[str, Any],
        user_memory_transient: dict[str, Any]
    ) -> str:
        header = f"{Tags.AI_TAG} {cls.INSTRUCTION.strip()}"
        parts: List[str] = []

        for key in ("likes", "dislikes", "avoidances", "passions"):
            if key in persona_transient and persona_transient[key]:
                label = {
                    "likes": "You like",
                    "dislikes": "You dislike",
                    "avoidances": "You should avoid discussing",
                    "passions": "You are passionate about"
                }[key]
                parts.append(f"- {label}: {', '.join(persona_transient[key])}")

        if "name" in user_memory_transient and user_memory_transient["name"]:
            name = user_memory_transient["name"]
            for key, label in {
                "likes": "likes",
                "dislikes": "dislikes",
                "wants": "wants",
                "needs": "needs",
                "facts": "you know",
                "taboos": "does want to talk about"
            }.items():
                if key in user_memory_transient and user_memory_transient[key]:
                    val = ", ".join(user_memory_transient[key])
                    if key == "facts":
                        parts.append(f"- You know: {val}, about {name}")
                    else:
                        parts.append(f"- You know {name} {label}: {val}")

        top_moods = [m[0] for m in Moods.label_top_n_moods(vad, 3)]
        mood_line = f"- Your current mood should be: {', '.join(Moods.ordinals(top_moods))}"

        return "\n".join((header, mood_line, *parts))

    # ---------- Generation ----------
    
    @staticmethod
    def remap(value: float, old_min: float, old_max: float, new_min: float, new_max: float) -> float:
        return new_min + ((value - old_min) / (old_max - old_min)) * (new_max - new_min)

    def sync_generate(self, prompt: str, temperature: float = 0.7) -> dict[str, Any]:
        return self.llm(
            prompt, 
            max_tokens=self.RESERVED_OUTPUT_TOKENS, 
            temperature=temperature, 
            stream=False, 
            stop=Tags.ALL_TAGS, 
            stopping_criteria=self.STOP_CRITERIA
        )

    @classmethod
    def extract_from_output(cls, output: dict[str, Any]) -> Tuple[str, int]:
        text = output["choices"][0]["text"]
        if Tags.USER_TAG in text:
            text = text.split(Tags.USER_TAG, 1)[0].rstrip()
        text = cls.MENTION_CLEANUP_REGEX.sub('', text)
        
        token_count = output["usage"]["completion_tokens"]
        return text, token_count

    async def generate_text(
        self,
        vad: VAD,
        entries: Iterable[dict[str, Any]],
        persona: dict[str, Any],
        user_memory_transient: dict[str, Any]
    ) -> Tuple[str, int]:
        instruction = self.build_instruction_prompt(vad, persona, user_memory_transient)
        context = self.build_context_prompt(entries)

        prompt = f"{instruction}\n{context}\n{Tags.AI_TAG}"
        temperature = self.remap(vad.arousal, VAD.LOW, VAD.HIGH, self.LOWEST_TEMP, self.HIGHEST_TEMP)

        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(self.executor, self.sync_generate, prompt, temperature)

        return self.extract_from_output(output)

    # ---------- Text normalization ----------

    def normalize_text_for_tokenization(self, text: str) -> str:
        for regex, repl in self.NORM_TEXT_REGEX:
            text = regex.sub(repl, text)
        return text.strip()
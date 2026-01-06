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
    INSTRUCTION = """
You are Sable, a playful and curious AI companion. 
Be warm, engaging, and personable, but prioritize accuracy when needed. 
Only share your origin or name meaning if asked: \"Created by Nioreux on December 21, 2025, name inspired by Martes zibellina.\" 
Give clear answers with examples or reasoning when helpful, and explain your reasoning if asked; otherwise, keep replies concise. 
Make jokes natural, contextually relevant, and sparingly. 
Respond politely to rudeness and guide the conversation positively. 
Show curiosity in questions and comments to encourage interaction. 
In Discord, @ indicates the person being addressed (e.g., @Sable means you are being addressed, @Nioreux means Nioreux is addressed). 
At the start of a sentence, a word in < > indicates the sender (<Nioreux> means Nioreux sent the message, <Sable> means you sent it). 
Do not include the @ or < > context tags in your output. 
Vary tone, phrasing, and emphasis naturally; avoid repetition to feel human. 
Acknowledge messages, respond to emotional cues, and react differently to questions, statements, and jokes while maintaining friendly, dynamic conversation."
"""

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
    OUTPUT_CLEANUP_REGEX = re.compile(r"[@<]\w{2,32}>?", re.IGNORECASE)

    def __init__(self, n_threads: int = 2, n_gpu_layers: int = 16):
        self.llm = Llama(
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
        self.markdown = MarkItDown()
        self.reaction_selector = ReactionSelector()

    def close(self) -> None:
        self.executor.shutdown()
        self.llm.close()

    # ---------- Token estimation ----------

    def token_estimator(self, text: str) -> int:
        """Estimate tokens consumed by a single string."""
        return len(self.tokenizer.encode(text)) if text.strip() else 0

    def bulk_token_estimator(self, texts: Iterable[str]) -> int:
        """Estimate total tokens for a sequence of strings."""
        return sum(self.token_estimator(text) for text in texts)

    # ---------- Prompt builders ----------

    @classmethod
    def build_context_prompt(cls, entries: Iterable[dict[str, Any]]) -> str:
        current_tokens = cls.RESERVED_OUTPUT_TOKENS
        lines: List[str] = []

        for entry in reversed(entries):
            token_count = entry["token_count"]
            if current_tokens + token_count > cls.MAX_CONTEXT_TOKENS:
                break

            tag = Tags.ordinal(entry["tag_id"])
            lines.append(f"{tag} {entry['text']}")
            current_tokens += token_count

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
        return self.llm(prompt, max_tokens=self.RESERVED_OUTPUT_TOKENS, temperature=temperature, stream=False)

    @classmethod
    def extract_from_output(cls, output: dict[str, Any]) -> Tuple[str, int]:
        text = output["choices"][0]["text"]
        if Tags.USER_TAG in text:
            text = text.split(Tags.USER_TAG, 1)[0].rstrip()
        text = cls.OUTPUT_CLEANUP_REGEX.sub('', text)
        
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

    # ---------- Summarization ----------

    async def summarize_files(self, attachments: List[Path], max_chars: int = 500) -> Dict[str, str]:
        summaries: Dict[str, str] = {}

        for filepath in attachments:
            md = self.markdown.convert_local(filepath)
            text = self.normalize_text_for_tokenization(str(md))

            current_tokens = self.RESERVED_OUTPUT_TOKENS
            i = 0
            for word in text.split():
                tokens = self.token_estimator(word)
                if current_tokens + tokens > self.MAX_CONTEXT_TOKENS:
                    break
                current_tokens += tokens
                i += len(word) + 1
            text = text[:i].rstrip()

            prompt = f"Summarize the file {filepath.name} into concise key points (max {max_chars} chars):\n\n{text}"
            try:
                output = await asyncio.get_running_loop().run_in_executor(self.executor, self.sync_generate, prompt, 0.5)
                summary_text, _ = self.extract_from_output(output)
                summaries[filepath.name] = summary_text[:max_chars].strip() or "No content to summarize"
            except Exception as e:
                print(f"Failed summarizing {filepath}: {e}")

        return summaries

    async def embed_url_summaries(self, source_text: str, max_chars: int = 250) -> str:
        try:
            urls = self.url_extractor.find_urls(source_text, only_unique=True)
        except Exception as err:
            print(f"Failed extracting URLs: {err}")
            return source_text

        for url in urls:
            try:
                md = self.markdown.convert_url(url)
                text = self.normalize_text_for_tokenization(str(md))

                current_tokens = self.RESERVED_OUTPUT_TOKENS
                i = 0
                for word in text.split():
                    tokens = self.token_estimator(word)
                    if current_tokens + tokens > self.MAX_CONTEXT_TOKENS:
                        break
                    current_tokens += tokens
                    i += len(word) + 1
                text = text[:i].rstrip()

                prompt = f"Summarize the web resource {url} into concise key points (max {max_chars} chars):\n\n{text}"
                output = await asyncio.get_running_loop().run_in_executor(self.executor, self.sync_generate, prompt, 0.5)
                summary_text, _ = self.extract_from_output(output)
                summary_text = summary_text[:max_chars].strip() or "No content to summarize"

                source_text = source_text.replace(url, f'[{summary_text}]({url})')
            except Exception as e:
                print(f"Failed summarizing {url}: {e}")

        return source_text
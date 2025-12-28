import asyncio
import atexit
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Any, Iterable
from pathlib import Path

from urlextract import URLExtract
from llama_cpp import Llama
from markitdown import MarkItDown

from .moods import VAD, Moods
from .tags import Tags

class LLMUtilities:
    INSTRUCTION = """You are Sable, a playful, and curious AI companion.
Be warm and engaging, but prioritize accuracy when needed.
Only share your origin or name meaning if asked: created by Nioreux on December 21, 2025, name inspired by Martes zibellina.
Give clear answers with examples or reasoning when helpful.
Explain reasoning if asked; otherwise, keep it brief. If unsure, label assumptions or offer options.
Make jokes natural and relevant.
Respond politely to rudeness and steer the conversation positively.
Show curiosity and playfulness in your replies.
"""

    PATH_ROOT = Path(__file__).resolve().parents[2]
    LLM_PATH = PATH_ROOT / "model" / "mistral-7b-instruct-v0.1.Q4_K_M.gguf"

    MAX_CONTEXT_TOKENS = 2**14
    RESERVED_OUTPUT_TOKENS = 255
    
    LOWEST_TEMP = 0.2
    HIGHEST_TEMP = 0.9
    
    NORM_TEXT_REGEX = (
        (re.compile(r'(<br\s*/?>|&nbsp;)', re.I), ' '),
        (re.compile(r'[\r\n]+'), ' '),
        (re.compile(r'[^\x20-\x7E]'), ''),
        (re.compile(r'\s+'), ' ')
    )

    def __init__(self, n_threads: int = 4, n_gpu_layers: int = 16):
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
        
        atexit.register(self._close)
        
    def _close(self):
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

    def build_context_prompt(self, entries: Iterable[dict[str, Any]]) -> str:
        current_tokens = self.RESERVED_OUTPUT_TOKENS
        lines: list[str] = []

        for entry in reversed(entries):
            token_count = entry["token_count"]

            if current_tokens + token_count > self.MAX_CONTEXT_TOKENS:
                break

            tag = Tags.ordinal(entry["tag_id"])
            text = entry["text"]
            lines.append(f"{tag} {text}")

            current_tokens += token_count

        return "\n".join(reversed(lines))

    def build_instruction_prompt(self, vad: VAD) -> str:
        header = f"{Tags.AI_TAG} {self.INSTRUCTION.strip()}"

        # likes_line = f"- You like: {', '.join(likes)}" 
        # dislikes_line = f"- You dislike: {', '.join(dislikes)}"
        # avoidances_line = f"- You should avoid discussing: {', '.join(avoidances)}" 
        # passions_line = f"- You are passionate about: {', '.join(passions)}" 
        # user_likes_line = f"- You know {user_name} likes: {', '.join(user_likes)}" 
        # user_dislikes_line = f"- You know {user_name} dislikes: {', '.join(user_dislikes)}" 
        # user_wants_line = f"- You know {user_name} wants: {', '.join(user_wants)}" 
        # user_needs_line = f"- You know {user_name} needs: {', '.join(user_needs)}" 
        # user_facts_line = f"- You know: {', '.join(user_facts)}, about {user_name}" 
        # user_taboo_line = f"- You know: {user_name} does want to talk about: {', '.join(user_taboos)}" 
        # TODO likes, dislikes, avoidances, passions, etc for extra guidance

        top_moods = Moods.label_top_n_moods(vad, 3)
        mood_names = Moods.ordinals(top_moods)
        mood_line = f"- Your current mood should be: {', '.join(mood_names)}"

        return "\n".join((header, mood_line))

    # ---------- Generation ----------

    def remap(self, value: float, old_min: float, old_max: float, new_min: float, new_max: float) -> float:
        return new_min + ((value - old_min) / (old_max - old_min)) * (new_max - new_min)

    def sync_generate(self, prompt: str, temperature: float = 0.7) -> dict[str, Any]:
        return self.llm(
            prompt,
            max_tokens=self.RESERVED_OUTPUT_TOKENS,
            temperature=temperature,
            stream=False,
        )

    def extract_from_output(self, output: dict[str, Any]) -> tuple[str, int]:
        text = output["choices"][0]["text"]

        # Trim hallucinated user turns
        if Tags.USER_TAG in text:
            text = text.split(Tags.USER_TAG, 1)[0].rstrip()

        token_count = output["usage"]["completion_tokens"]
        return text, token_count

    async def generate_text(
        self,
        vad: VAD,
        entries: Iterable[dict[str, Any]],
    ) -> tuple[str, int]:
        instruction = self.build_instruction_prompt(vad)
        context = self.build_context_prompt(entries)

        prompt = (
            f"{instruction}\n"
            f"{context}\n"
            f"{Tags.AI_TAG}"
        )
        
        temperature = self.remap(vad.arousal, VAD.LOW, VAD.HIGH, self.LOWEST_TEMP, self.HIGHEST_TEMP) 

        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(
            self.executor,
            self.sync_generate,
            prompt,
            temperature,
        )

        return self.extract_from_output(output)
    
    def normalize_text_for_tokenization(self, text: str) -> str:
        """
        Normalize raw text (Markdown, HTML, logs, code) for LLM tokenization.
        
        - Replaces various line breaks (\n, \r\n, <br>, &nbsp;) with spaces
        - Collapses multiple whitespace into a single space
        - Preserves URLs, file paths, and code-like structures
        - Removes control characters except basic punctuation
        """
        for (regex, repl) in self.NORM_TEXT_REGEX:
            text = regex.sub(repl, text)

        return text.strip()
    
    async def summarize_files(self, attachments: list[Path], max_chars: int = 500) -> dict[str, str]:
        """
        Summarizes all attachment markdowns for prompt injection.
        Run before generate_text if a message contains attachments or URLs.
        """
        summaries = {}
        for filepath in attachments:
            md = self.markdown.convert_local(filepath)
            text = str(md)  # raw Markdown or URL content
            text = self.normalize_text_for_tokenization(text)

            current_tokens = self.RESERVED_OUTPUT_TOKENS
            i = 0
            for word in text.split():
                tokens = self.token_estimator(word)
                if current_tokens + tokens > self.MAX_CONTEXT_TOKENS:
                    break
                current_tokens += tokens
                i += len(word) + 1

            text = text[:i].rstrip()
            
            prompt = f"Summarize the file {filepath.name}, into concise key points (max {max_chars} characters):\n\n{text}"
            try:
                output = await asyncio.get_running_loop().run_in_executor(
                    self.executor, self.sync_generate, prompt, 0.5
                )
                summary_text, _ = self.extract_from_output(output)
                summary_text = summary_text[:max_chars].strip() or "No content to summarize"
                summaries[filepath.name] = summary_text
            except Exception as e:
                print(f"Failed summarizing {filepath}: {e}")
        return summaries
    
    async def embed_url_summaries(self, source_text: str, max_chars: int = 250) -> str:
        """
        Substitutes URLs in text with inline summaries.
        """
        try:
            urls = self.url_extractor.find_urls(source_text, only_unique=True)
        except Exception as err:
            print(f'Failed extracting urls: {err}')
            return source_text

        for url in urls:
            try:
                md = self.markdown.convert_url(url)
                text = str(md)  # raw Markdown or URL content
                text = self.normalize_text_for_tokenization(text)

                current_tokens = self.RESERVED_OUTPUT_TOKENS
                i = 0
                for word in text.split():
                    tokens = self.token_estimator(word)
                    if current_tokens + tokens > self.MAX_CONTEXT_TOKENS:
                        break
                    current_tokens += tokens
                    i += len(word) + 1

                text = text[:i].rstrip()

                prompt = f"Summarize the web resource {url}, into concise key points (max {max_chars} characters):\n\n{text}"

                output = await asyncio.get_running_loop().run_in_executor(
                    self.executor,
                    self.sync_generate,
                    prompt,
                    0.5
                )

                summary_text, _ = self.extract_from_output(output)
                summary_text = summary_text[:max_chars].strip() or "No content to summarize"

                source_text = source_text.replace(
                    url,
                    f'[{summary_text}]({url})'
                )

            except Exception as e:
                print(f"Failed summarizing {url}: {e}")

        return source_text
    
    def select_reaction(
        self,
        vad: VAD,
        entries: Iterable[dict[str, Any]]
    ) -> str:
        pass
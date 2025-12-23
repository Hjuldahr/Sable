import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List
import discord
from llama_cpp import Llama

from components.ai.Tags import Tags
from components.db import DAO  # your updated DAO with reactions field

class Core:
    CONTEXT_TOKENS = 32768
    MAX_HISTORY = 1000
    PRUNE_HISTORY = 750
    RESERVED_OUTPUT_TOKENS = 255

    INSTRUCTION = "Respond as the AI persona naturally, concisely, and contextually."

    def __init__(
        self,
        ai_user_id: int,
        ai_user_name='Sable',
        model_path=r'..\..\model\mistral-7b-instruct-v0.1.Q4_K_M.gguf',
        n_threads=4,
    ):
        self.ai_user_name = ai_user_name
        self.ai_user_id = ai_user_id

        # Deferred assignment
        self.persona: Dict[str, Any] = {}
        self.conversation_history: List[Dict[str, Any]] = []
        self.user_memory: Dict[int, Dict[str, Any]] = {}

        # DAO for persistence
        self.dao: DAO = DAO()
        asyncio.create_task(self.dao.init())

        # LLM
        self.llm = Llama(
            model_path,
            n_ctx=self.CONTEXT_TOKENS,
            n_threads=n_threads,
            n_gpu_layers=32,
            verbose=False
        )
        self.tokenizer = self.llm.tokenizer()
        self.tag_token_counts = {
            Tags.SYS: self.token_counter(Tags.SYS_TAG),
            Tags.AI: self.token_counter(Tags.AI_TAG),
            Tags.USER: self.token_counter(Tags.USER_TAG)
        }

        self.executor = ThreadPoolExecutor(max_workers=n_threads, thread_name_prefix='sable')
        self.reserved_tokens = self.RESERVED_OUTPUT_TOKENS
        self.conversation_history_lock = asyncio.Lock()

    # ---- Conversation History ----
    async def add_to_conversation_history(self, entry: Dict[str, Any]):
        async with self.conversation_history_lock:
            self.conversation_history.append(entry)
            if len(self.conversation_history) > self.MAX_HISTORY:
                self.conversation_history = self.conversation_history[-self.PRUNE_HISTORY:]
            # Persist in DB
            await self.dao.upsert_conversation_history(entry)

    async def clear_conversation_history(self):
        async with self.conversation_history_lock:
            self.conversation_history.clear()
            # Optional: truncate in DB
            # await self.dao.truncate_conversation_history()  # implement if needed

    # ---- Formatting / Prompt Building ----
    def format_line(self, entry: Dict[str, Any]):
        channel_name = entry.get('channel_name', 'unknown')
        user_name = entry.get('user_name', 'unknown')
        raw_text = entry.get('raw_text', '')
        return f"{Tags.TAGS.get(entry['role_id'], '')} [{channel_name}] {user_name}: {raw_text}"

    def build_prompt(self) -> str:
        temp_history = self.conversation_history[::-1]
        prompt_stack = [Tags.AI_TAG]
        current_token_count = self.reserved_tokens

        for entry in temp_history:
            if current_token_count + entry.get('token_count', 0) > self.CONTEXT_TOKENS:
                break
            current_token_count += entry.get('token_count', 0)
            prompt_stack.append(self.format_line(entry))

        prompt_stack.append(self.INSTRUCTION)
        return '\n'.join(reversed(prompt_stack))

    # ---- LLM Generation ----
    def _generate(self, prompt: str) -> Dict:
        return self.llm(prompt, max_tokens=256, stream=False)

    def extract_from_output(self, output: Dict) -> tuple[str, int]:
        response = output['choices'][0]['text']
        # Remove trailing user tags if present
        if Tags.USER_TAG in response:
            response = response.split(Tags.USER_TAG, 1)[0].rstrip()
        token_count = output['usage']['completion_tokens']
        return response, token_count

    # ---- Discord Interaction ----
    async def listen(self, message: discord.Message):
        """Process incoming message: update history, user memory, etc."""
        user_id = message.author.id
        user_name = message.author.name
        raw_text = message.content
        channel_id = message.channel.id
        channel_name = getattr(message.channel, 'name', 'DM')

        # Update UserMemory
        user_memory = self.user_memory.get(user_id, {
            'user_id': user_id,
            'user_name': user_name,
            'nickname': user_name,
            'interests': [],
            'learned_facts': {},
            'interaction_count': 0,
            'last_seen_at': datetime.now(timezone.utc).timestamp()
        })
        user_memory['user_name'] = user_name
        user_memory['interaction_count'] += 1
        user_memory['last_seen_at'] = datetime.now(timezone.utc).timestamp()
        self.user_memory[user_id] = user_memory
        await self.dao.upsert_user_memory(user_memory)

        # Estimate token count
        token_count = self.token_counter(raw_text)

        # Update conversation history
        entry = {
            'message_id': message.id,
            'user_id': user_id,
            'user_name': user_name,
            'channel_id': channel_id,
            'channel_name': channel_name,
            'raw_text': raw_text,
            'token_count': token_count,
            'role_id': Tags.USER,
            'sent_at': message.created_at.timestamp(),
            'context': {},
            'was_edited': int(message.edited_at is not None),
            'reactions': {}
        }
        await self.add_to_conversation_history(entry)

    async def response(self) -> Dict[str, Any]:
        """Generate a response using persona, user memory, and conversation history."""
        prompt = self.build_prompt()
        output = await asyncio.get_running_loop().run_in_executor(self.executor, self._generate, prompt)
        response_text, token_count = self.extract_from_output(output)

        # Record AI message
        entry = {
            'message_id': int(datetime.now().timestamp()*1000),  # pseudo unique
            'user_id': self.ai_user_id,
            'user_name': self.ai_user_name,
            'channel_id': 0,
            'channel_name': 'AI',
            'raw_text': response_text,
            'token_count': token_count,
            'role_id': Tags.AI,
            'sent_at': datetime.now(timezone.utc).timestamp(),
            'context': {},
            'was_edited': 0,
            'reactions': {}
        }
        await self.add_to_conversation_history(entry)
        return {'text': response_text, 'token_count': token_count}

    async def add_react(self, message_id: int, emoji: str, user_id: int):
        """Add reaction to a conversation history entry."""
        # Update in-memory
        async with self.conversation_history_lock:
            for entry in self.conversation_history:
                if entry['message_id'] == message_id:
                    reactions = entry.get('reactions', {})
                    reactions.setdefault(emoji, [])
                    if user_id not in reactions[emoji]:
                        reactions[emoji].append(user_id)
                    entry['reactions'] = reactions
                    # Persist
                    await self.dao.upsert_conversation_history(entry)
                    break

    # ---- Token utilities ----
    def token_counter(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    # ---- Cleanup ----
    def close(self):
        self.executor.shutdown(cancel_futures=True)
        self.llm.close()
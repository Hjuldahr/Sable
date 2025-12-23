"""
ai
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import discord
from llama_cpp import Llama
from markitdown import MarkItDown

from components.ai.tags import Tags
from components.db.sqlite_dao import SQLiteDAO  # your updated DAO with reactions field

class AICore:
    """
    Central AI Core
    """
    CONTEXT_TOKENS = 32768
    MAX_HISTORY = 1000
    PRUNE_HISTORY = 750
    RESERVED_OUTPUT_TOKENS = 255

    INSTRUCTION = f"""You are Sable, a friendly, playful, and curious AI companion. 
    Be warm and engaging, but prioritize accuracy when needed. 
    Only share your origin or name meaning if asked: created by Nioreux on December 21, 2025, name inspired by Martes zibellina. 
    Give clear answers with examples or reasoning when helpful. 
    Explain reasoning if asked; otherwise, keep it brief. 
    If unsure, label assumptions or offer options. 
    Make jokes natural and relevant. 
    Respond politely to rudeness and steer the conversation positively. 
    Show curiosity and playfulness in your replies."""
    
    def __init__(
        self,
        discord_client: discord.Client,
        ai_user_id: int,
        ai_user_name='Sable',
        model_path=r'.\model\mistral-7b-instruct-v0.1.Q4_K_M.gguf',
        n_threads=4,
    ):
        """
        Args:
            discord_client (discord.Client): The client used for connection
            ai_user_id (int): The Discord Bot ID 
            ai_user_name (str, optional): The Discord Bot Username. Defaults to 'Sable'.
            model_path (str, optional): Path to the LLM model file. Defaults to r'.\model\mistral-7b-instruct-v0.1.Q4_K_M.gguf'.
            n_threads (int, optional): Multithreading Allocation. Defaults to 4.
        """
        self.discord_client = discord_client

        self.ai_user_name = ai_user_name
        self.ai_user_id = ai_user_id

        # Deferred assignment
        self.persona: Dict[str, Any] = {}
        self.conversation_history: List[Dict[str, Any]] = []
        self.user_memory: Dict[int, Dict[str, Any]] = {}

        # DAO for persistence
        self.dao = SQLiteDAO()

        # MarkItDown for file interpreting
        self.md = MarkItDown()

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
        self.instruction_token_count = self.token_counter(self.INSTRUCTION)

        self.reserved_tokens = self.RESERVED_OUTPUT_TOKENS
        self.reserved_tokens += self.instruction_token_count
        self.reserved_tokens += self.tag_token_counts[Tags.AI]
        self.reserved_tokens += self.tag_token_counts[Tags.SYS]
        
        self.executor = ThreadPoolExecutor(max_workers=n_threads, thread_name_prefix=self.ai_user_name)
        
        self.conversation_history_lock = asyncio.Lock()

    async def init(self):
        """Async initialization. Calls dao init."""
        if self.dao:
            await self.dao.init()

    # ---- Conversation History ----
    async def add_to_conversation_history(self, entry: Dict[str, Any]):
        """
        Async conversation history update.\n
        Automatically truncates memory and persists to db.

        Args:
            entry (Dict[str, Any]): Entry to be stored
        """
        async with self.conversation_history_lock:
            self.conversation_history.append(entry)
            if len(self.conversation_history) > self.MAX_HISTORY:
                self.conversation_history = self.conversation_history[-self.PRUNE_HISTORY:]
            # Persist in DB
            await self.dao.upsert_conversation_history(entry)

    async def clear_conversation_history(self):
        """Async conversation history mass deletion."""
        async with self.conversation_history_lock:
            self.conversation_history.clear()
            await self.dao.delete_all_conversation_history()

    # ---- Formatting / Prompt Building ----
    def format_line(self, entry: Dict[str, Any]) -> str:
        """
        Formats entry for prompt injection

        Args:
            entry (Dict[str, Any]): Conversation entry data

        Returns:
            str: Formatted prompt entry
        """
        channel_name = entry.get('channel_name', 'unknown')
        user_name = entry.get('user_name', 'unknown')
        raw_text = entry.get('raw_text', '')
        return f"{Tags.TAGS[entry['role_id']]} [{channel_name}] {user_name}: {raw_text}"

    def build_prompt(self) -> str:
        """
        Composes a prompt from history and other metrics to feed into the LLM

        Returns:
            str: LLM Prompt
        """
        #TODO add ai mood, conversation subject, etc indicators into instructions
        temp_history = self.conversation_history[::-1]
        prompt_stack = [Tags.AI_TAG]
        current_token_count = self.reserved_tokens

        for entry in temp_history:
            token_count = self.tag_token_counts[entry['role_id']] + entry.get('token_count', 0)
            
            if token_count > self.CONTEXT_TOKENS:
                break
            current_token_count += token_count
            prompt_stack.append(self.format_line(entry))

        prompt_stack.append(f'{Tags.SYS_TAG} {self.INSTRUCTION}')
        return '\n'.join(reversed(prompt_stack))

    # ---- LLM Generation ----
    def _generate(self, prompt: str) -> Dict:
        """
        LLM call wrapper\n
        Llama.call() is natively a blocking operation

        Args:
            prompt (str): The prompt used for LLM generation

        Returns:
            Dict: The result produced by the LLM
        """
        # TODO dynamic temperature based on mood thresholds
        return self.llm(prompt, max_tokens=256, stream=False)

    def extract_from_output(self, output: Dict) -> tuple[str, int]:

        response = output['choices'][0]['text']
        # Remove trailing user tags if present
        if Tags.USER_TAG in response:
            response = response.split(Tags.USER_TAG, 1)[0].rstrip()
        token_count = output['usage']['completion_tokens']
        return response, token_count

    def strip_mentions(self, raw_text: str) -> str:
        """Removes Discord mention tags from text

        Args:
            raw_text (str): Original Discord message

        Returns:
            str: Cleaned message
        """
        return raw_text.replace(f'<@!{self.ai_user_id}>', '').replace(f'<@{self.ai_user_id}>', '').strip()

    # ---- Discord Interaction ----
    async def listen(self, message: discord.Message):
        """
        Process incoming message: update history, user memory, etc.

        Args:
            message (discord.Message): Message to be processed
        """
        user_id = message.author.id
        user_name = message.author.name
        text = self.strip_mentions(message.content)
        channel_id = message.channel.id
        channel_name = getattr(message.channel, 'name', 'DM')

        reactions = []
        if message.reactions:
            for reaction in message.reactions:
                emoji = str(reaction.emoji)
                users = []
                async for user in reaction.users():
                    if user.id != self.ai_user_id:
                        users.append(user.mention)
                reactions.append({'emoji': emoji, 'users': users})

        attachments = {}
        if message.attachments:
            parent_path = Path(__file__).resolve().parents[2] / 'data' / 'attachments'
            for attachment in message.attachments:
                child_path = parent_path / attachment.filename
                try:
                    await attachment.save(fp=child_path, use_cached=True)
                    md_text = self.md.convert_local(child_path)
                    attachments[attachment.filename] = md_text
                except Exception as e:
                    print(f'Error Encountered During Attachment Download [{child_path}]: {e}')
        
        #TODO Update Persona State

        # Update UserMemory
        user_memory = self.user_memory.get(user_id, {
            'user_id': user_id,
            'user_name': user_name,
            'nickname': user_name,
            'interests': [], #TODO update
            'learned_facts': {}, #TODO update
            'interaction_count': 0, 
            'last_seen_at': datetime.now(timezone.utc).timestamp()
        })
        #user_memory['user_name'] = user_name
        user_memory['interaction_count'] += 1
        user_memory['last_seen_at'] = datetime.now(timezone.utc).timestamp()
        self.user_memory[user_id] = user_memory
        await self.dao.upsert_user_memory(user_memory)

        # Estimate token count
        token_count = self.token_counter(text)

        # Update conversation history
        entry = {
            'message_id': message.id,
            'user_id': user_id,
            'user_name': user_name,
            'channel_id': channel_id,
            'channel_name': channel_name,
            'raw_text': text,
            'token_count': token_count,
            'role_id': Tags.USER,
            'sent_at': message.created_at.timestamp(),
            'context': {},
            'was_edited': int(message.edited_at is not None),
            'reactions': reactions,
            'attachments': attachments
        }
        await self.add_to_conversation_history(entry)

    async def response(self) -> Dict[str, Any]:
        """Generate a response using persona, user memory, and conversation history.

        Returns:
            Dict[str, Any]: Response Generated by LLM
        """
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
        return {'response_text': response_text} #Include file creation and more if needed in future

    async def react(self, message_id: int):
        """Add reaction to a conversation history entry."""
        # TODO decide if its react worthy based on AI persona
        heuristic = 0 # Replace with a heuristic measure calculated from message
        threshold = 1 # Replace with AI mood (more likely to emote if mood is high)

        if heuristic <= threshold:
            # TODO choose emote based on persona
            # TODO apply emote to message
            pass

        # TODO Update in-memory
        """
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
        """

    # ---- Token utilities ----
    def token_counter(self, text: str) -> int:
        """
        Estimates the number of tokens that a string would consume

        Args:
            text (str): Text to be tokenized

        Returns:
            int: Quantity of tokens
        """
        return len(self.tokenizer.encode(text))

    # ---- Cleanup ----
    def close(self):
        """Terminates the LLM and its utilities"""
        self.executor.shutdown(cancel_futures=True)
        self.llm.close()
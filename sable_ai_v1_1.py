import atexit
import json
from typing import Any
import aiosqlite
from datetime import datetime, timezone
from llama_cpp import Llama
import asyncio
from concurrent.futures import ThreadPoolExecutor
import signal

# --- Tags ---
class Tags:
    SYS = 0
    USER = 1
    AI = 2
    SYS_TAG = "### instruction:"
    USER_TAG = "### user:"
    AI_TAG = "### assistant:"
    TAGS = {
        SYS: SYS_TAG,
        USER: USER_TAG,
        AI: AI_TAG
    }

# --- DTO ---
class HistoryDTO:
    def __init__(self, tag_id: int, channel_id: Union[int, None], channel_name: str,
                 message_id: Union[int, None], timestamp: datetime, user_id: int,
                 user_name: str, raw_text: str, token_count: int):
        self.tag_id = tag_id
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.message_id = message_id
        self.timestamp = timestamp
        self.user_id = user_id
        self.user_name = user_name
        self.raw_text = raw_text
        self.token_count = token_count

# --- DAO ---
class HistoryDAO:
    def __init__(self, db_path=r".\data\history-v1-1.db"):
        self.db_path = db_path
        self.conn: aiosqlite.Connection = None

    async def init(self):
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS Persona (
                id INTEGER PRIMARY KEY CHECK(id = 1),  -- ensures singleton
                user_id INTEGER DEFAULT 1452493514050113781, -- discord id
                name TEXT DEFAULT 'Sable',
                personality_traits JSON,               -- e.g., {"friendly":0.8,"humorous":0.5}
                tone_style TEXT,                        -- e.g., "playful"
                principles JSON,                        -- e.g., {"honesty":true,"empathetic":true}
                default_response_length INTEGER DEFAULT 255,
                created_at INTEGER DEFAULT (strftime('%s','now')),  -- UNIX epoch
                updated_at INTEGER
            );
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS UserMemory (
                user_id INTEGER PRIMARY KEY,             -- unique per user
                user_name TEXT,                          -- current Discord/username
                nickname TEXT,                           -- how AI addresses this user
                interests JSON,                          -- e.g., {"topics":["tech","anime"]}
                learned_facts JSON,                      -- e.g., {"favorite_color":"teal"}
                interaction_count INTEGER DEFAULT 0,
                last_seen_at INTEGER                      -- UNIX epoch
            );
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ConversationHistory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,                         -- links to UserMemory
                channel_id INTEGER,                       -- Discord channel or conversation ID
                message_id INTEGER,                       -- Discord message ID
                timestamp INTEGER,                        -- UNIX epoch
                raw_text TEXT,
                token_count INTEGER,
                role_id INTEGER                           -- "user" or "ai"
            );
        """)
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_history_user_id ON ConversationHistory(user_id);")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_history_channel_id ON ConversationHistory(channel_id);")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_user_last_seen ON UserMemory(last_seen_at);")
        await self.conn.commit()

    async def load_persona(self) -> dict[str, Any]:
        self.conn.row_factory = aiosqlite.Row
        cursor = await self.conn.execute(
            "SELECT user_id, name, personality_traits, tone_style, principles, default_response_length, created_at, updated_at FROM Persona;"
        )
        row = await cursor.fetchone()
        if not row:
            return None

        persona = dict(row)
        persona['personality_traits'] = json.loads(persona['personality_traits'] or "{}")
        persona['principles'] = json.loads(persona['principles'] or "{}")
        persona['created_at'] = datetime.fromtimestamp(persona['created_at'], tz=timezone.utc)
        if persona.get('updated_at'):
            persona['updated_at'] = datetime.fromtimestamp(persona['updated_at'], tz=timezone.utc)

        return persona
    
    async def save_persona(self, persona: dict[str, Any]) -> None:
        personality_traits = json.dumps(persona.get('personality_traits', {}))
        tone_style = persona.get('tone_style', '')
        principles = json.dumps(persona.get('principles', {}))
        updated_at = int(datetime.now(timezone.utc).timestamp())
        
        await self.conn.execute(
            """
            UPDATE Persona
            SET personality_traits = ?,
                tone_style = ?,
                principles = ?,
                updated_at = ?
            WHERE id = 1;
            """,
            (personality_traits, tone_style, principles, updated_at)
        )
        await self.conn.commit()
        
    async def load_persona(self) -> dict[str, Any]:
        self.conn.row_factory = aiosqlite.Row
        cursor = await self.conn.execute(
            "SELECT user_id, name, personality_traits, tone_style, principles, default_response_length, created_at, updated_at FROM Persona;"
        )
        row = await cursor.fetchone()
        if not row:
            return None

        persona = dict(row)
        persona['personality_traits'] = json.loads(persona['personality_traits'] or "{}")
        persona['principles'] = json.loads(persona['principles'] or "{}")
        persona['created_at'] = datetime.fromtimestamp(persona['created_at'], tz=timezone.utc)
        if persona.get('updated_at'):
            persona['updated_at'] = datetime.fromtimestamp(persona['updated_at'], tz=timezone.utc)

        return persona

    async def close(self):
        if self.conn:
            await self.conn.close()

    def close_sync(self):
        if self.conn:
            self.conn.close()

# --- EOS class ---
class Sable:
    INSTRUCTION = (
        f"{Tags.SYS_TAG} You are Sable, a friendly and helpful AI assistant. "
        "You answer questions clearly and accurately, can write and explain code, "
        "provide reasoning for your answers, and avoid making up information. "
        "Only respond based on reliable knowledge or indicate when you do not know."
    )
    CONTEXT_TOKENS = 32768
    MAX_HISTORY = 1000
    HISTORY_PRUNE = 750
    RESERVED_OUTPUT_TOKENS = 512

    def __init__(self, ai_user_name: str, ai_user_id: int, db_path="history.db"):
        self.ai_user_name = ai_user_name
        self.ai_user_id = ai_user_id

        self.llm = Llama(
            r'.\EOS\model\mistral-7b-instruct-v0.1.Q4_0.gguf',
            n_ctx=self.CONTEXT_TOKENS,
            n_threads=8,
            n_gpu_layers=32,
            verbose=False
        )
        self.tokenizer = self.llm.tokenizer()
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix='eos')

        self.dao = HistoryDAO(db_path)
        self.history = []
        self.reserved_tokens = self.RESERVED_OUTPUT_TOKENS
        self.local_timezone = datetime.now().astimezone().tzinfo
        self.lock = asyncio.Lock()
        
        atexit.register(self.close)

    async def init(self):
        """Initialize DAO and load history from DB."""
        await self.dao.init()
        self.history = await self.dao.load_all()

    async def add_to_history(
        self,
        tag_id: int,
        channel_id: Union[int, None],
        channel_name: str,
        message_id: Union[int, None],
        timestamp: datetime,
        user_id: int,
        user_name: str,
        text: str,
        token_count: int
    ) -> None:
        dto = HistoryDTO(tag_id, channel_id, channel_name, message_id, timestamp, user_id, user_name, text, token_count)
        async with self.lock:
            self.history.append(dto)
            await self.dao.add_entry(dto)
            if len(self.history) > self.MAX_HISTORY:
                self.history = self.history[-self.HISTORY_PRUNE:]

    def token_counter(self, prompt: str) -> int:
        return len(self.tokenizer.encode(prompt))

    def build_prompt(self) -> str:
        prompt_stack = [Tags.AI_TAG]
        current_token_count = self.reserved_tokens
        for dto in reversed(self.history):
            if current_token_count + dto.token_count > self.CONTEXT_TOKENS:
                break
            current_token_count += dto.token_count
            text = f'{Tags.TAGS[dto.tag_id]} [{dto.channel_name}] {dto.user_name}: {dto.raw_text}'
            prompt_stack.append(text)
        prompt_stack.append(self.INSTRUCTION)
        return '\n'.join(reversed(prompt_stack))

    def _generate(self, prompt: str) -> Dict:
        return self.llm(prompt, max_tokens=256, stream=False)

    def extract_from_output(self, output: Dict) -> tuple[str, int]:
        response = output['choices'][0]['text']
        response = response.split(Tags.USER_TAG, 1)[0].rstrip() if Tags.USER_TAG in response else response
        token_count = output['usage']['completion_tokens']
        return response, token_count

    async def listen_respond(
        self,
        channel_id: Union[int, None],
        channel_name: str,
        message_id: Union[int, None],
        query_timestamp: datetime,
        user_id: int,
        user_name: str,
        query: str
    ) -> str:
        token_count = self.token_counter(query)
        await self.add_to_history(Tags.USER, channel_id, channel_name, message_id, query_timestamp, user_id, user_name, query, token_count)

        prompt = self.build_prompt()
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(self.executor, self._generate, prompt)
        response, token_count = self.extract_from_output(output)

        await self.add_to_history(Tags.AI, channel_id, channel_name, None, datetime.now(self.local_timezone), self.ai_user_id, self.ai_user_name, response, token_count)
        return response

    async def respond(self) -> str:
        prompt = self.build_prompt()
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(self.executor, self._generate, prompt)
        response, token_count = self.extract_from_output(output)
        
        await self.add_to_history(Tags.AI, -1, "N/A", None, datetime.now(self.local_timezone), self.ai_user_id, self.ai_user_name, response, token_count)
        return response

    async def listen(
        self,
        channel_id: Union[int, None],
        channel_name: str,
        message_id: Union[int, None],
        query_timestamp: datetime,
        user_id: int,
        user_name: str,
        dialogue: str
    ) -> None:
        token_count = self.token_counter(dialogue)
        await self.add_to_history(Tags.USER, channel_id, channel_name, message_id, query_timestamp, user_id, user_name, dialogue, token_count)

    def close(self) -> None:
        """Close all resources safely."""
        try:
            self.executor.shutdown(wait=True, cancel_futures=True)
        except Exception as e:
            print(f'Error during executor shutdown: {e}')
        try:
            self.llm.close()
        except Exception as e:
            print(f'Error during Llama closure: {e}')
        try:
            self.dao.close_sync()
        except Exception as e:
            print(f'Error during DAO closure: {e}')

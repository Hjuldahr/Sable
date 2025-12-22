from datetime import datetime, timezone
import json
from typing import Any
import aiosqlite

class DAO:
    def __init__(self, db_path=r".\data\history-v1-1.db"):
        self.db_path = db_path
        self.conn: aiosqlite.Connection = None

    async def init(self):
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS Persona (
                id INTEGER PRIMARY KEY CHECK(id = 1),  -- ensures singleton
                user_id INTEGER DEFAULT 1452493514050113781, -- discord id
                AI_name TEXT DEFAULT 'Sable',
                personality_traits Text,               -- e.g., JSON {"friendly":0.8,"humorous":0.5}
                tone_style TEXT,                        -- e.g., "playful"
                principles Text,                        -- e.g., JSON ["honesty","empathetic"]
                default_response_length INTEGER DEFAULT 255,
                created_at INTEGER DEFAULT (strftime('%s','now')),  -- UNIX epoch
                updated_at INTEGER DEFAULT (strftime('%s','now'))
            );
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS UserMemory (
                user_id INTEGER PRIMARY KEY,             -- unique per user
                user_name TEXT,                          -- current Discord/username
                nickname TEXT,                           -- how AI addresses this user
                interests Text,                          -- e.g., JSON ["tech","anime"]
                learned_facts Text,                      -- e.g., JSON {"favorite_color":"teal"}
                interaction_count INTEGER DEFAULT 0,
                last_seen_at INTEGER DEFAULT (strftime('%s','now')) -- UNIX epoch
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
        persona['updated_at'] = datetime.fromtimestamp(persona['updated_at'], tz=timezone.utc)

        return persona
    
    async def save_persona(self, persona: dict[str, Any]) -> None:
        personality_traits_json = json.dumps(persona.get('personality_traits', {}))
        tone_style = persona.get('tone_style', '')
        principles_json = json.dumps(persona.get('principles', {}))
        updated_at = int(datetime.now(timezone.utc).timestamp())
        
        await self.conn.execute(
            "UPDATE Persona SET personality_traits = ?, tone_style = ?, principles = ?, updated_at = ? WHERE id = 1;",
            (personality_traits_json, tone_style, principles_json, updated_at)
        )
        await self.conn.commit()
        
    async def load_persona(self) -> dict[str, Any]:
        self.conn.row_factory = aiosqlite.Row
        cursor = await self.conn.execute(
            "SELECT user_id, AI_name, personality_traits, tone_style, principles, default_response_length, created_at, updated_at FROM Persona;"
        )
        row = await cursor.fetchone()
        if not row:
            return None

        persona = dict(row)
        persona['personality_traits'] = json.loads(persona['personality_traits'] or r"{}")
        persona['principles'] = json.loads(persona['principles'] or r"{}")
        persona['created_at'] = datetime.fromtimestamp(persona['created_at'], tz=timezone.utc)
        if persona.get('updated_at'):
            persona['updated_at'] = datetime.fromtimestamp(persona['updated_at'], tz=timezone.utc)

        return persona

    async def load_user_memories(self) -> list[dict[str, Any]]:
        self.conn.row_factory = aiosqlite.Row
        cursor = await self.conn.execute(
            "SELECT user_id, user_name, nickname, interests, learned_facts, interaction_count, last_seen_at FROM UserMemory;"
        )
        rows = await cursor.fetchall()
        user_memories = []

        for row in rows:
            user_memory = dict(row)
            user_memory['interests'] = json.loads(user_memory.get('interests') or "[]")
            user_memory['learned_facts'] = json.loads(user_memory.get('learned_facts') or "{}")
            if user_memory.get('last_seen_at'):
                user_memory['last_seen_at'] = datetime.fromtimestamp(user_memory['last_seen_at'], tz=timezone.utc)
            else:
                user_memory['last_seen_at'] = None
            user_memories.append(user_memory)

        return user_memories
    
    async def save_user_memory(self, user_memory: dict):
        interests_json = json.dumps(user_memory.get('interests', []))
        learned_facts_json = json.dumps(user_memory.get('learned_facts', {}))
        last_seen = int(user_memory.get('last_seen_at', datetime.now(timezone.utc).timestamp()))
        
        await self.conn.execute(
            """
            INSERT INTO UserMemory (user_id, user_name, nickname, interests, learned_facts, interaction_count, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                user_name = excluded.user_name,
                nickname = excluded.nickname,
                interests = excluded.interests,
                learned_facts = excluded.learned_facts,
                interaction_count = excluded.interaction_count,
                last_seen_at = excluded.last_seen_at;
            """,
            (
                user_memory['user_id'],
                user_memory.get('user_name', ''),
                user_memory.get('nickname', ''),
                interests_json,
                learned_facts_json,
                user_memory.get('interaction_count', 0),
                last_seen
            )
        )
        await self.conn.commit()
        
    async def delete_user_memory(self, user_id: int):
        await self.conn.execute(
            "DELETE FROM UserMemory WHERE user_id = ?;",
            (user_id,)
        )
        await self.conn.commit()
        
    

    async def close(self):
        if self.conn:
            await self.conn.close()

    def close_sync(self):
        if self.conn:
            self.conn.close()

"""
sqlite_dao
"""
from pathlib import Path
import json
from datetime import datetime, timezone
from typing import Any, List, Optional

import aiosqlite

class SQLiteDAO:
    """
    Handles asynchronous connections and statements for SQLite
    """
    def __init__(self):
        self.db_path = Path(__file__).resolve().parents[2] / 'data' / 'database.db'
        self.conn: aiosqlite.Connection | None = None

    async def init(self):
        """Async initialization. Connects to SQLite and creates missing tables"""
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row

        await self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS Persona (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            user_id INTEGER,
            AI_name TEXT,
            personality_traits TEXT DEFAULT '{}',
            tone_style TEXT,
            principles TEXT DEFAULT '[]',
            default_response_length INTEGER DEFAULT 255,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            updated_at INTEGER DEFAULT (strftime('%s','now'))
        );

        INSERT INTO Persona (id, user_id, AI_name, tone_style, default_response_length)
        VALUES (1, 1452493514050113781, 'Sable', 'playful', 255)
        ON CONFLICT(id) DO NOTHING;

        CREATE TABLE IF NOT EXISTS UserMemory (
            user_id INTEGER PRIMARY KEY,
            user_name TEXT,
            nickname TEXT,
            interests TEXT DEFAULT '[]',
            learned_facts TEXT DEFAULT '{}',
            interaction_count INTEGER DEFAULT 0,
            last_seen_at INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS ConversationHistory (
            message_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            channel_id INTEGER,
            sent_at INTEGER,
            raw_text TEXT,
            context TEXT DEFAULT '{}',
            token_count INTEGER,
            role_id INTEGER,
            was_edited INTEGER DEFAULT 0,
            reactions TEXT DEFAULT '{}',
            attachments TEXT DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_history_user_id ON ConversationHistory(user_id);
        CREATE INDEX IF NOT EXISTS idx_history_channel_id ON ConversationHistory(channel_id);
        CREATE INDEX IF NOT EXISTS idx_user_last_seen ON UserMemory(last_seen_at);
        """)

        await self.conn.commit()

    # ---- Persona Methods ----

    async def select_persona(self) -> Optional[dict[str, Any]]:
        """Load singleton persona as dict with JSON fields decoded."""
        cursor = await self.conn.execute("""
            SELECT user_id, AI_name, personality_traits, tone_style, principles, 
                   default_response_length, created_at, updated_at
            FROM Persona;
        """)
        row = await cursor.fetchone()
        if not row:
            return None

        persona = dict(row)
        persona['personality_traits'] = json.loads(persona.get('personality_traits', '{}'))
        persona['principles'] = json.loads(persona.get('principles', '[]'))
        persona['created_at'] = datetime.fromtimestamp(persona['created_at'], tz=timezone.utc)
        persona['updated_at'] = datetime.fromtimestamp(persona['updated_at'], tz=timezone.utc) if persona.get('updated_at') else None
        return persona

    async def update_persona(self, persona: dict[str, Any]) -> None:
        """Update persona JSON fields and timestamp."""
        personality_traits_json = json.dumps(persona.get('personality_traits', {}))
        principles_json = json.dumps(persona.get('principles', []))
        tone_style = persona.get('tone_style', '')
        updated_at = int(datetime.now(timezone.utc).timestamp())

        await self.conn.execute("""
            UPDATE Persona
            SET personality_traits = ?, tone_style = ?, principles = ?, updated_at = ?
            WHERE id = 1;
        """, (personality_traits_json, tone_style, principles_json, updated_at))
        await self.conn.commit()

    # ---- UserMemory Methods ----

    async def select_all_user_memories(self) -> List[dict[str, Any]]:
        """Return all user memories as list of dicts with JSON decoded."""
        cursor = await self.conn.execute("""
            SELECT user_id, user_name, nickname, interests, learned_facts, interaction_count, last_seen_at
            FROM UserMemory;
        """)
        rows = await cursor.fetchall()
        user_memories = []
        for row in rows:
            um = dict(row)
            um['interests'] = json.loads(um.get('interests', '[]'))
            um['learned_facts'] = json.loads(um.get('learned_facts', '{}'))
            um['last_seen_at'] = datetime.fromtimestamp(um['last_seen_at'], tz=timezone.utc) if um.get('last_seen_at') else None
            user_memories.append(um)
        return user_memories

    async def upsert_user_memory(self, user_memory: dict[str, Any]) -> None:
        """Insert or update a user memory (UPSERT)."""
        interests_json = json.dumps(user_memory.get('interests', []))
        learned_facts_json = json.dumps(user_memory.get('learned_facts', {}))
        last_seen = int(user_memory.get('last_seen_at', datetime.now(timezone.utc).timestamp()))

        await self.conn.execute("""
            INSERT INTO UserMemory (user_id, user_name, nickname, interests, learned_facts, interaction_count, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                user_name = excluded.user_name,
                nickname = excluded.nickname,
                interests = excluded.interests,
                learned_facts = excluded.learned_facts,
                interaction_count = excluded.interaction_count,
                last_seen_at = excluded.last_seen_at;
        """, (
            user_memory['user_id'],
            user_memory.get('user_name', ''),
            user_memory.get('nickname', ''),
            interests_json,
            learned_facts_json,
            user_memory.get('interaction_count', 0),
            last_seen
        ))
        await self.conn.commit()

    async def delete_user_memory(self, user_id: int) -> None:
        """Delete a user memory by user_id."""
        await self.conn.execute(
            "DELETE FROM UserMemory WHERE user_id = ?;", (user_id,)
        )
        await self.conn.commit()

    # ---- ConversationHistory Methods ----

    async def threshold_select_conversation_history(self, token_count_threshold: int) -> List[dict[str, Any]]:
        """Select recent conversation rows until a cumulative token threshold is reached."""
        cursor = await self.conn.execute("""
            SELECT message_id, user_id, channel_id, sent_at, raw_text, context, token_count, role_id, was_edited, reactions, attachments
            FROM ConversationHistory
            ORDER BY sent_at DESC
            LIMIT 1000;
        """)
        rows = await cursor.fetchall()
        total_tokens = 0
        safe_rows = []

        for row in rows:
            ch = dict(row)
            if total_tokens + (ch.get('token_count') or 0) > token_count_threshold:
                break
            total_tokens += ch.get('token_count', 0)
            ch['context'] = json.loads(ch.get('context', '{}'))
            ch['reactions'] = json.loads(ch.get('reactions', '{}'))
            ch['attachments'] = json.loads(ch.get('attachments', '{}'))
            safe_rows.append(ch)

        return safe_rows[::-1]  # return oldest -> newest

    async def upsert_conversation_history(self, conversation_history: dict[str, Any]) -> None:
        """Insert or update Conversation History"""
        sent_at = int(conversation_history.get('sent_at', datetime.now(timezone.utc).timestamp()))
        context_json = json.dumps(conversation_history.get('context', {}))
        reactions_json = json.dumps(conversation_history.get('reactions', {}))  
        attachments_json = json.loads(conversation_history.get('attachments', '{}'))

        await self.conn.execute("""
            INSERT INTO ConversationHistory 
                (message_id, user_id, channel_id, sent_at, raw_text, context, token_count, role_id, was_edited, reactions, attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                user_id = excluded.user_id,
                channel_id = excluded.channel_id,
                sent_at = excluded.sent_at,
                raw_text = excluded.raw_text,
                context = excluded.context,
                token_count = excluded.token_count,
                role_id = excluded.role_id,
                was_edited = excluded.was_edited,
                reactions = excluded.reactions,
                attachments = excluded.attachments;
        """, (
            conversation_history['message_id'],
            conversation_history['user_id'],
            conversation_history['channel_id'],
            sent_at,
            conversation_history['raw_text'],
            context_json,
            conversation_history.get('token_count', 0),
            conversation_history['role_id'],
            conversation_history.get('was_edited', 0),
            reactions_json,
            attachments_json
        ))
        await self.conn.commit()

    async def delete_conversation_history(self, message_id: int) -> None:
        """Delete conversation row by message_id."""
        await self.conn.execute(
            "DELETE FROM ConversationHistory WHERE message_id = ?;", (message_id,)
        )
        await self.conn.commit()

    # ---- Cleanup ----

    async def close(self) -> None:
        """Closes SQLite connection."""
        if self.conn:
            await self.conn.close()
            self.conn = None

# sqlite_dao
from pathlib import Path
import json
from datetime import datetime, timezone
from typing import Any, List, Optional
import aiosqlite

from components.ai.moods import Moods


class SQLiteDAO:
    def __init__(self):
        self.db_path = Path(__file__).resolve().parents[2] / 'data' / 'database.db'
        self.conn: Optional[aiosqlite.Connection] = None

    async def init(self):
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row

        await self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS Persona (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            user_id INTEGER DEFAULT 1452493514050113781,
            AI_name TEXT DEFAULT 'Sable',
            personality_traits TEXT DEFAULT '{}',
            valence REAL DEFAULT 0.5,
            arousal REAL DEFAULT 0.5,
            dominance REAL DEFAULT 0.5,
            mood_id INT DEFAULT 0,
            likes TEXT DEFAULT '[]',
            dislikes TEXT DEFAULT '[]',
            interests TEXT DEFAULT '[]',
            memories TEXT DEFAULT '[]',
            default_response_length INTEGER DEFAULT 255,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            updated_at INTEGER DEFAULT (strftime('%s','now'))
        );

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

    # ---- Helper Methods ----

    @staticmethod
    def _json_load(value: str, default: Any) -> Any:
        try:
            return json.loads(value) if value else default
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _json_dump(value: Any) -> str:
        return json.dumps(value)

    @staticmethod
    def _to_ts(dt: Optional[datetime]) -> int:
        return int(dt.timestamp()) if dt else int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    def _from_ts(ts: Optional[int]) -> Optional[datetime]:
        return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None

    # ---- Persona Methods ----

    async def select_persona(self) -> Optional[dict[str, Any]]:
        cursor = await self.conn.execute("SELECT * FROM Persona;")
        row = await cursor.fetchone()
        if not row:
            return None
        persona = dict(row)
        for field, default in [('personality_traits', {}), ('likes', []), ('dislikes', []),
                               ('interests', []), ('memories', [])]:
            persona[field] = self._json_load(persona.get(field), default)
        persona['created_at'] = self._from_ts(persona.get('created_at'))
        persona['updated_at'] = self._from_ts(persona.get('updated_at'))
        return persona

    async def update_persona(self, persona: dict[str, Any]) -> None:
        fields = ['personality_traits', 'likes', 'dislikes', 'interests', 'memories']
        json_fields = {f: self._json_dump(persona.get(f, {} if f == 'personality_traits' else [])) for f in fields}
        updated_at = self._to_ts(None)

        await self.conn.execute("""
            UPDATE Persona
            SET AI_name = ?,
                personality_traits = ?,
                valence = ?,
                arousal = ?,
                dominance = ?,
                mood_id = ?,
                likes = ?,
                dislikes = ?,
                interests = ?,
                memories = ?,
                default_response_length = ?,
                updated_at = ?
            WHERE id = 1;
        """, (
            persona.get('AI_name', 'Sable'),
            json_fields['personality_traits'],
            persona.get('valence', 0.5),
            persona.get('arousal', 0.5),
            persona.get('dominance', 0.5),
            persona.get('mood_id', Moods.NEUTRAL),
            json_fields['likes'],
            json_fields['dislikes'],
            json_fields['interests'],
            json_fields['memories'],
            persona.get('default_response_length', 255),
            updated_at
        ))
        await self.conn.commit()

    # ---- UserMemory Methods ----

    async def select_all_user_memories(self) -> List[dict[str, Any]]:
        cursor = await self.conn.execute("SELECT * FROM UserMemory;")
        rows = await cursor.fetchall()
        memories = []
        for row in rows:
            um = dict(row)
            um['interests'] = self._json_load(um.get('interests'), [])
            um['learned_facts'] = self._json_load(um.get('learned_facts'), {})
            um['last_seen_at'] = self._from_ts(um.get('last_seen_at'))
            memories.append(um)
        return memories

    async def upsert_user_memory(self, user_memory: dict[str, Any]) -> None:
        interests_json = self._json_dump(user_memory.get('interests', []))
        learned_facts_json = self._json_dump(user_memory.get('learned_facts', {}))
        last_seen = self._to_ts(user_memory.get('last_seen_at'))

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
        await self.conn.execute("DELETE FROM UserMemory WHERE user_id = ?;", (user_id,))
        await self.conn.commit()

    # ---- ConversationHistory Methods ----

    async def threshold_select_conversation_history(self, token_count_threshold: int) -> List[dict[str, Any]]:
        cursor = await self.conn.execute("SELECT * FROM ConversationHistory ORDER BY sent_at DESC LIMIT 1000;")
        rows = await cursor.fetchall()
        total_tokens = 0
        safe_rows = []
        for row in rows:
            ch = dict(row)
            if total_tokens + (ch.get('token_count') or 0) > token_count_threshold:
                break
            total_tokens += ch.get('token_count', 0)
            for field in ['context', 'reactions', 'attachments']:
                ch[field] = self._json_load(ch.get(field), {})
            safe_rows.append(ch)
        return safe_rows[::-1]

    async def upsert_conversation_history(self, conversation_history: dict[str, Any]) -> None:
        sent_at = self._to_ts(conversation_history.get('sent_at'))
        context_json = self._json_dump(conversation_history.get('context', {}))
        reactions_json = self._json_dump(conversation_history.get('reactions', {}))
        attachments_json = self._json_dump(conversation_history.get('attachments', {}))

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
        await self.conn.execute("DELETE FROM ConversationHistory WHERE message_id = ?;", (message_id,))
        await self.conn.commit()

    async def delete_all_conversation_history(self) -> None:
        await self.conn.execute("DELETE FROM ConversationHistory;")
        await self.conn.commit()

    # ---- Cleanup ----

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None
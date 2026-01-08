# sqlite_dao_refactored.py
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
from typing import Any, Generator, Iterable
import aiofiles
import aiosqlite
import discord
import markitdown

class SQLiteDAO:
    PATH_ROOT = Path(__file__).resolve().parents[2]
    SETUP_SCRIPT_PATH = PATH_ROOT / 'components' / 'db' / 'setup.sqlite'
    DB_PATH = PATH_ROOT / 'data' / 'sqlite' / 'database.db'
    
    MID = markitdown.MarkItDown()
    
    ran_setup = False

    @classmethod
    async def create(cls) -> SQLiteDAO:
        self = cls.__new__(cls)
        if not cls.ran_setup:
            await cls.run_setup_script()
        return self

    @classmethod
    async def run_setup_script(cls):
        try:
            if cls.SETUP_SCRIPT_PATH.exists():
                async with aiosqlite.connect(cls.DB_PATH) as db:
                    script = cls.SETUP_SCRIPT_PATH.read_text()
                    await db.executescript(script)
                    await db.commit()
                    cls.ran_setup = True
        except aiosqlite.Error | OSError as err:
            print(f"Schema setup failed, rolled back: {err}")
            await cls.rollback(db)

    # --- Helpers ---
    @staticmethod
    def _json_load(value: str | None, default: Any) -> Any:
        if value in (None, ""):
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _json_dump(value: Any) -> str:
        return json.dumps(value) if value is not None else ""

    @staticmethod
    def _to_ts(value: datetime | None, required: bool = False) -> int | None:
        dt = value if value is not None else (datetime.now(timezone.utc) if required else None)
        return int(dt.timestamp()) if dt else None

    @staticmethod
    def _from_ts(value: int | None, required: bool = False) -> datetime | None:
        if value is not None:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return datetime.now(timezone.utc) if required else None

    @staticmethod
    def _to_bool(value: int) -> bool:
        return bool(value)

    @staticmethod
    def _from_bool(value: bool) -> int:
        return int(value)

    @staticmethod
    async def rollback(db: aiosqlite.Connection | None):
        if db is None:
            return
        try:
            if db.in_transaction:
                await db.rollback()
                print("Transaction rollback successful")
        except Exception as e:
            print(f"Transaction rollback failed: {e}")

    # --- Generic fetch helpers ---
    @staticmethod
    async def fetch_one_dict(db: aiosqlite.Connection, query: str, params: tuple | None = None) -> dict[str, Any] | None:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
        
    @staticmethod
    async def fetch_one_func(db: aiosqlite.Connection, func: Any, query: str, params: tuple | None = None) -> dict[str, Any] | None:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return func(dict(row)) if row else None
        
    @staticmethod
    async def fetch_one_comp(db: aiosqlite.Connection, func: Any, query: str, params: tuple | None = None) -> dict[str, Any] | None:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return await func(db, dict(row)) if row else None

    @staticmethod
    async def fetch_all_dicts(db: aiosqlite.Connection, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            return [dict(row) async for row in cursor]
        
    @staticmethod
    async def fetch_all_func(db: aiosqlite.Connection, func: Any, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            return [func(dict(row)) async for row in cursor]
        
    @staticmethod
    async def fetch_all_comp(db: aiosqlite.Connection, func: Any, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            return [await func(db, dict(row)) async for row in cursor]
            
    # --- Guild ---
    
            
    # --- Text Channels ---
    
    
            
    # --- Messages ---
    
    
        
    # --- Discord Message Mentions (Helper) ---
    
    @classmethod
    async def upsert_message_mentions(cls, db: aiosqlite.Connection, message: discord.Message):
        try:
            await db.executemany(
                """
                INSERT INTO DiscordMessageMentions(
                    message_id, mention_text, mention_id
                ) VALUES (?, ?, ?) 
                ON CONFLICT(message_id, mention_id) DO NOTHING
                """,
                ((
                    message.id,
                    mention.name,
                    mention.id
                ) for mention in message.mentions)
            )
        except aiosqlite.Error as err:
            print(f"Insert message mentions failed: {err}")
            await cls.rollback(db)
    
    @classmethod
    async def select_mentions_by_message_id(cls, db: aiosqlite.Connection, message_id: int) -> list[dict[str,Any]] | None:
        try:
            rows = await cls.fetch_all_dicts(
                db, "SELECT * FROM DiscordMessageMentions WHERE message_id=?", (message_id,)
            )
            return rows
        except aiosqlite.Error as err:
            print(f"Select mentions failed: {err}")
            return None
    
    @classmethod
    async def delete_mentions_by_message_id(cls, db: aiosqlite.Connection, message_id: int):
        try:
            await db.execute(
                "DELETE FROM DiscordMessageMentions WHERE message_id=?", (message_id,)
            )
        except aiosqlite.Error as err:
            print(f"Delete mentions failed: {err}")
            cls.rollback(db)
        
    # --- Attachments (Helper) ---
    def attachments_to_tuple(attachment_data: dict[str,discord.Message | markitdown.DocumentConverterResult | discord.Attachment | Path]) -> tuple[discord.Message | markitdown.DocumentConverterResult | discord.Attachment | Path]:
        attachment: discord.Attachment = attachment_data['attachment']
        message: discord.Message = attachment_data['message']
        path: Path = attachment_data['path']
        markdown: markitdown.DocumentConverterResult = attachment_data['markdown']

        return (
            attachment.id, message.id,
            attachment.url, attachment.proxy_url, str(path.resolve()),
            attachment.filename, attachment.content_type, attachment.size, attachment.is_spoiler,
            markdown.title, str(markdown)
        )
    
    @classmethod
    async def upsert_attachments(
        cls, db: aiosqlite.Connection, attachments_data: list[dict[str,discord.Message | markitdown.DocumentConverterResult | discord.Attachment | Path]]
    ):
        try:
            await db.executemany(
                """
                INSERT INTO DiscordAttachments(
                    attachment_id, message_id,
                    source_url, source_proxy_url, local_path,
                    file_name, content_type, size, is_spoiler,
                    title, markdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(attachment_id) DO UPDATE SET
                    source_url=EXCLUDED.source_url,
                    source_proxy_url=EXCLUDED.source_proxy_url,
                    local_path=EXCLUDED.local_path,
                    file_name=EXCLUDED.file_name,
                    content_type=EXCLUDED.content_type,
                    size=EXCLUDED.size,
                    is_spoiler=EXCLUDED.is_spoiler,
                    title=EXCLUDED.title,
                    markdown=EXCLUDED.markdown
                """,
                (cls.attachments_to_tuple(attachment_data) for attachment_data in attachments_data)
            )
        except aiosqlite.Error as err:
            print(f"Upsert attachments failed: {err}")
            await cls.rollback(db)
            
    @classmethod
    async def select_attachments_by_message_id(
        cls, db: aiosqlite.Connection, message_id: int
    ) -> list[dict[str, Any]]:
        return await cls.fetch_all_dicts(
            db,
            "SELECT * FROM DiscordAttachments WHERE message_id=?",
            (message_id,)
        )
        
    @classmethod
    async def delete_attachments_by_message_id(
        cls, db: aiosqlite.Connection, message_id: int
    ):
        await db.execute(
            "DELETE FROM DiscordAttachments WHERE message_id=?",
            (message_id,)
        )
            
    # --- Reactions ---
    
    @classmethod
    async def upsert_reactions(cls, db: aiosqlite.Connection, message: discord.Message):
        try:
            await db.executemany(
                """
                INSERT INTO DiscordReactions(message_id, emoji, count, users_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(message_id, emoji) DO UPDATE SET
                    count=EXCLUDED.count,
                    users_json=EXCLUDED.users_json
                """,
                (
                    (
                        message.id,
                        str(r.emoji),
                        r.count,
                        cls._json_dump([u.id for u in await r.users().flatten()])
                    )
                    for r in message.reactions
                )
            )
        except aiosqlite.Error as err:
            print(f"Upsert reactions failed: {err}")
            await cls.rollback(db)
            
    @classmethod
    async def select_reactions_by_message_id(
        cls, db: aiosqlite.Connection, message_id: int
    ) -> list[dict[str, Any]]:
        return await cls.fetch_all_dicts(
            db,
            "SELECT * FROM DiscordReactions WHERE message_id=?",
            (message_id,)
        )
        
    @classmethod
    async def delete_reactions_by_message_id(
        cls, db: aiosqlite.Connection, message_id: int
    ):
        await db.execute(
            "DELETE FROM DiscordReactions WHERE message_id=?",
            (message_id,)
        )
        
    # --- Context ---
    
    @classmethod
    async def select_context_window(
        cls,
        channel_id: int,
        limit: int = 50,
        before_ts: int | None = None
    ) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                params = [channel_id]
                where = "channel_id=?"

                if before_ts:
                    where += " AND created_at<?"
                    params.append(before_ts)

                query = f"""
                    SELECT *
                    FROM DiscordMessage
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                params.append(limit)

                rows = await cls.fetch_all_dicts(db, query, tuple(params))
                rows.reverse()  # chronological

                for row in rows:
                    row['created_at'] = cls._from_ts(row['created_at'])
                    row['edited_at'] = cls._from_ts(row['edited_at'])

                return rows
        except aiosqlite.Error as err:
            print(f"Select context window failed: {err}")
            return []
            
    # --- User Memory ---
    @classmethod
    async def upsert_user_memory(cls, memory: dict[str, Any]):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO UserMemory(user_id, user_name, nickname, interaction_count, last_seen_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        nickname=EXCLUDED.nickname,
                        interaction_count=EXCLUDED.interaction_count,
                        last_seen_at=EXCLUDED.last_seen_at
                    """,
                    (
                        memory['user_id'],
                        memory['user_name'],
                        memory['nickname'],
                        memory['interaction_count'],
                        cls._to_ts(memory['last_seen_at'])
                    )
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert user memory failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def select_user_memory(cls, user_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_one_dict(db, "SELECT * FROM UserMemory WHERE user_id=?", (user_id,))
        except aiosqlite.Error as err:
            print(f"Select user memory failed: {err}")
            return None

    @classmethod
    async def delete_user_memory(cls, user_id: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM UserMemory WHERE user_id=?", (user_id,))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete user memory failed: {err}")
            await cls.rollback(db)

    # --- Persona & Persona Transient ---
    @classmethod
    async def update_persona(cls, persona: dict[str, Any]):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    """
                    UPDATE Persona
                    SET personality_traits=?, subject_history=?, updated_on=strftime('%s','now')
                    WHERE id=1
                    """,
                    (
                        cls._json_dump(persona['personality_traits']),
                        cls._json_dump(persona['subject_history'])
                    )
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Update persona failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def select_persona(cls) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                row = await cls.fetch_one_dict(db, "SELECT * FROM Persona WHERE id=1")
                if row:
                    return {
                        'personality_traits': cls._json_load(row['personality_traits'], []),
                        'subject_history': cls._json_load(row['subject_history'], [])
                    }
                return None
        except aiosqlite.Error as err:
            print(f"Select persona failed: {err}")
            return None

    @classmethod
    async def insert_persona_transient(cls, entry: dict[str, Any]):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO PersonaTransient(entry, category)
                    VALUES (?, ?)
                    ON CONFLICT(entry, category) DO UPDATE SET
                        added_on=strftime('%s','now')
                    """,
                    (entry['entry'], entry['category'])
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Insert persona transient failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def select_persona_transient(cls, category: str) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_dicts(db, "SELECT * FROM PersonaTransient WHERE category=? ORDER BY added_on", (category,))
        except aiosqlite.Error as err:
            print(f"Select persona transient failed: {err}")
            return []
        
    @classmethod
    async def select_persona_transient_all(cls) -> dict[str,list[dict[str, Any]]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                rows = await cls.fetch_all_dicts(
                    db,
                    "SELECT * FROM PersonaTransient ORDER BY category, added_on"
                )
                grouped = defaultdict(list)
                for row in rows:
                    cat = row.pop('category')
                    grouped[cat].append(row)
                return dict(grouped)
        except aiosqlite.Error as err:
            print(f"Select persona transient failed: {err}")
            return []

    @classmethod
    async def delete_persona_transient(cls, threshold_days: int):
        ts = cls._to_ts(datetime.now(timezone.utc) - timedelta(days=threshold_days))
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM PersonaTransient WHERE added_on<?", (ts,))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete persona transient failed: {err}")
            await cls.rollback(db)

    # --- User Memory Transient ---
    @classmethod
    async def insert_memory_transient(cls, memory: dict[str, Any]):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO UserMemoryTransient(user_id, entry, category)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, entry, category) DO UPDATE SET
                        added_on=strftime('%s','now')
                    """,
                    (memory['user_id'], memory['entry'], memory['category'])
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Insert memory transient failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def select_memory_transient(cls, user_id: int, category: str) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_dicts(
                    db,
                    "SELECT * FROM UserMemoryTransient WHERE user_id=? AND category=? ORDER BY added_on",
                    (user_id, category)
                )
        except aiosqlite.Error as err:
            print(f"Select memory transient failed: {err}")
            return []

    @classmethod
    async def select_memory_transient_category_grouped(cls, user_id: int) -> dict[str, list[dict[str, Any]]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                rows = await cls.fetch_all_dicts(
                    db,
                    "SELECT * FROM UserMemoryTransient WHERE user_id=? ORDER BY category, added_on",
                    (user_id,)
                )
                grouped = defaultdict(list)
                for row in rows:
                    cat = row.pop('category')
                    grouped[cat].append(row)
                return dict(grouped)
        except aiosqlite.Error as err:
            print(f"Select memory transient failed: {err}")
            return {}

    @classmethod
    async def delete_memory_transient(cls, threshold_days: int):
        ts = cls._to_ts(datetime.now(timezone.utc) - timedelta(days=threshold_days))
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM UserMemoryTransient WHERE added_on<?", (ts,))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete memory transient failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def dump(cls) -> io.BytesIO | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                buffer = io.BytesIO()
                async for line in db.iterdump():
                    buffer.write(f"{line}\n".encode('utf-8'))
                buffer.seek(0)
                return buffer
                
        except aiosqlite.Error as err:
            print(f"Dump failed: {err}")
            return None
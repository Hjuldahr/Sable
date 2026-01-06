# sqlite_dao_refactored.py
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable
import aiofiles
import aiosqlite
import discord

class SQLiteDAO:
    PATH_ROOT = Path(__file__).resolve().parents[2]
    SETUP_SCRIPT_PATH = PATH_ROOT / 'components' / 'db' / 'setup.sqlite'
    DB_PATH = PATH_ROOT / 'data' / 'sqlite' / 'database.db'
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
    async def fetch_all_dicts(db: aiosqlite.Connection, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            return [dict(row) async for row in cursor]

    # --- Guilds ---
    @classmethod
    async def upsert_guild(cls, guild: discord.Guild):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO DiscordGuilds(
                        guild_id, guild_name, guild_description,
                        created_at, nsfw_level, verification_level, filesize_limit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        guild_name = EXCLUDED.guild_name,
                        guild_description = EXCLUDED.guild_description,
                        nsfw_level = EXCLUDED.nsfw_level,
                        verification_level = EXCLUDED.verification_level,
                        filesize_limit = EXCLUDED.filesize_limit
                    """,
                    (
                        guild.id,
                        guild.name,
                        guild.description or 'No Description Found',
                        cls._to_ts(guild.created_at),
                        guild.nsfw_level.name,
                        guild.verification_level.name,
                        guild.filesize_limit
                    )
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert guild failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def select_guild(cls, guild_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                row = await cls.fetch_one_dict(db, "SELECT * FROM DiscordGuilds WHERE guild_id=?", (guild_id,))
                if row:
                    row['created_at'] = cls._from_ts(row['created_at'])
                return row
        except aiosqlite.Error as err:
            print(f"Select guild failed: {err}")
            return None

    @classmethod
    async def select_all_guilds(cls) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                rows = await cls.fetch_all_dicts(db, "SELECT * FROM DiscordGuilds")
                for r in rows:
                    r['created_at'] = cls._from_ts(r['created_at'])
                return rows
        except aiosqlite.Error as err:
            print(f"Select all guilds failed: {err}")
            return []

    @classmethod
    async def delete_guild(cls, guild_id: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM DiscordGuilds WHERE guild_id=?", (guild_id,))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete guild failed: {err}")
            await cls.rollback(db)

    # --- Text Channels ---
    @classmethod
    async def upsert_text_channel(cls, channel: discord.TextChannel, permissions: discord.Permissions):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                permissions_json = cls._json_dump(dict(permissions))
                await db.execute(
                    """
                    INSERT INTO DiscordTextChannels(
                        channel_id, guild_id, channel_name, channel_topic,
                        channel_type, is_nsfw, permissions_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        channel_topic = EXCLUDED.channel_topic,
                        channel_type = EXCLUDED.channel_type,
                        permissions_json = EXCLUDED.permissions_json,
                        is_nsfw = EXCLUDED.is_nsfw
                    """,
                    (
                        channel.id,
                        channel.guild.id,
                        channel.name,
                        channel.topic or 'Topic not provided',
                        channel.type.name,
                        cls._from_bool(channel.is_nsfw),
                        permissions_json,
                        cls._to_ts(channel.created_at)
                    )
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert text channel failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def select_text_channel(cls, guild_id: int, channel_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                row = await cls.fetch_one_dict(
                    db,
                    "SELECT * FROM DiscordTextChannels WHERE guild_id=? AND channel_id=?",
                    (guild_id, channel_id)
                )
                if row:
                    row['created_at'] = cls._from_ts(row['created_at'])
                    row['is_nsfw'] = cls._to_bool(row['is_nsfw'])
                    row['permissions'] = cls._json_load(row['permissions'])
                return row
        except aiosqlite.Error as err:
            print(f"Select text channel failed: {err}")
            return None

    @classmethod
    async def select_all_text_channels(cls, guild_id: int) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                rows = await cls.fetch_all_dicts(db, "SELECT * FROM DiscordTextChannels WHERE guild_id=?", (guild_id,))
                for r in rows:
                    r['created_at'] = cls._from_ts(r['created_at'])
                    r['is_nsfw'] = cls._to_bool(r['is_nsfw'])
                    r['permissions'] = cls._json_load(r['permissions'])
                return rows
        except aiosqlite.Error as err:
            print(f"Select all text channels failed: {err}")
            return []

    @classmethod
    async def delete_text_channel(cls, guild_id: int, channel_id: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    "DELETE FROM DiscordTextChannels WHERE guild_id=? AND channel_id=?",
                    (guild_id, channel_id)
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete text channel failed: {err}")
            await cls.rollback(db)

    # --- Messages & Attachments ---
    @classmethod
    async def upsert_message(cls, message: discord.Message, token_count: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                reactions_json = cls._json_dump([{'emoji': str(r.emoji), 'count': r.count, 'me': r.me} for r in message.reactions])
                reference_id = (message.reference.message_id or -1) if message.reference else -1

                await db.execute(
                    """
                    INSERT INTO DiscordMessage(
                        message_id, references_message_id, user_id, channel_id,
                        text, token_count, reactions, created_at, edited_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(message_id) DO UPDATE SET
                        references_message_id=EXCLUDED.references_message_id,
                        text=EXCLUDED.text,
                        token_count=EXCLUDED.token_count,
                        reactions=EXCLUDED.reactions,
                        edited_at=EXCLUDED.edited_at
                    """,
                    (
                        message.id,
                        reference_id,
                        message.author.id,
                        message.channel.id,
                        message.clean_content,
                        token_count,
                        reactions_json,
                        cls._to_ts(message.created_at, required=True),
                        cls._to_ts(message.edited_at)
                    )
                )

                for attachment in message.attachments:
                    if not attachment.ephemeral:
                        await cls.upsert_attachment(db, message.id, attachment, Path(attachment.filename))

                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert message failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def upsert_attachment(cls, db: aiosqlite.Connection, message_id: int, attachment: discord.Attachment, path: Path):
        try:
            await db.execute(
                """
                INSERT INTO DiscordAttachments(
                    attachment_id, message_id, source_url, source_proxy_url,
                    local_path, title, content_type, file_name, description,
                    is_spoiler, size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(attachment_id) DO UPDATE SET
                    source_url=EXCLUDED.source_url,
                    source_proxy_url=EXCLUDED.source_proxy_url,
                    local_path=EXCLUDED.local_path,
                    title=EXCLUDED.title,
                    content_type=EXCLUDED.content_type,
                    file_name=EXCLUDED.file_name,
                    description=EXCLUDED.description,
                    is_spoiler=EXCLUDED.is_spoiler,
                    size=EXCLUDED.size
                """,
                (
                    attachment.id, message_id, attachment.url, attachment.proxy_url,
                    str(path), attachment.title, attachment.content_type,
                    attachment.filename, attachment.description, attachment.is_spoiler,
                    attachment.size
                )
            )
        except aiosqlite.Error as err:
            print(f"Upsert attachment failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def select_message(cls, message_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                row = await cls.fetch_one_dict(db, "SELECT * FROM DiscordMessage WHERE message_id=?", (message_id,))
                if row:
                    row['created_at'] = cls._from_ts(row['created_at'])
                    row['edited_at'] = cls._from_ts(row['edited_at'])
                return row
        except aiosqlite.Error as err:
            print(f"Select message failed: {err}")
            return None
        
    @classmethod
    async def select_reply(cls, user_id: int, references_message_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                row = await cls.fetch_one_dict(db, "SELECT * FROM DiscordMessage WHERE user_id=? AND references_message_id=?", (user_id, references_message_id))
                if row:
                    row['created_at'] = cls._from_ts(row['created_at'])
                    row['edited_at'] = cls._from_ts(row['edited_at'])
                return row
        except aiosqlite.Error as err:
            print(f"Select reply failed: {err}")
            return None

    @classmethod
    async def select_messages_by_channel(cls, channel_id: int) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                rows = await cls.fetch_all_dicts(db, "SELECT * FROM DiscordMessage WHERE channel_id=?", (channel_id,))
                for r in rows:
                    r['created_at'] = cls._from_ts(r['created_at'])
                    r['edited_at'] = cls._from_ts(r['edited_at'])
                return rows
        except aiosqlite.Error as err:
            print(f"Select messages failed: {err}")
            return []

    @classmethod
    async def delete_message(cls, message_id: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM DiscordMessage WHERE message_id=?", (message_id,))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete message failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def update_message_reactions(cls, message_id: int, reactions: list[discord.Reaction]):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                reactions_json = cls._json_dump([{'emoji': str(r.emoji), 'count': r.count, 'me': r.me} for r in reactions])
                await db.execute("UPDATE DiscordMessage SET reactions=? WHERE message_id=?", (reactions_json, message_id))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Update reactions failed: {err}")
            await cls.rollback(db)

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
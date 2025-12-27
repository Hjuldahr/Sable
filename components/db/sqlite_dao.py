# sqlite_dao_refactor.py
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import aiosqlite
import discord

class SQLiteDAO:
    PATH_ROOT = Path(__file__).resolve().parents[2]
    MODEL_PATH = PATH_ROOT / 'model' / 'mistral-7b-instruct-v0.1.Q4_K_M.gguf'

    def __init__(self):
        asyncio.run(self.run_setup_script())

    async def run_setup_script(self):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                if self.SETUP_SCRIPT_PATH.exists():
                    script = self.SETUP_SCRIPT_PATH.read_text()
                    if script.strip():
                        await db.executescript(script)
                        await db.commit()
            except (aiosqlite.Error, OSError) as err:
                await db.rollback()
                print(f"Schema setup failed, rolled back: {err}")

    # --- Helpers ---
    @staticmethod
    def _json_load(value: str, default: Any) -> Any:
        try:
            return json.loads(value) if value else default
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _json_dump(value: Any) -> str:
        return json.dumps(value) if value is not None else ""

    @staticmethod
    def _to_ts(value: datetime | None, required: bool = False) -> int | None:
        dt = value or (datetime.now(timezone.utc) if required else None)
        return int(dt.timestamp()) if dt else None

    @staticmethod
    def _from_ts(value: int | None, required: bool = False) -> datetime | None:
        return datetime.fromtimestamp(value, tz=timezone.utc) if value is not None else (datetime.now(timezone.utc) if required else None)

    @staticmethod
    def _to_bool(value: int) -> bool:
        return bool(value)

    @staticmethod
    def _from_bool(value: bool) -> int:
        return int(value)

    # --- Guilds ---
    async def upsert_guild(self, guild: discord.Guild):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute(
                    """INSERT INTO DiscordGuilds(guild_id, guild_name, guild_description, created_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(guild_id) DO UPDATE SET
                           guild_name = EXCLUDED.guild_name,
                           guild_description = EXCLUDED.guild_description;""",
                    (guild.id, guild.name, guild.description, self._to_ts(guild.created_at))
                )
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Upsert guild failed: {err}")

    async def select_guild(self, guild_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                async with db.execute(
                    "SELECT * FROM DiscordGuilds WHERE guild_id=?;", (guild_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    return {
                        **dict(row),
                        'created_at': self._from_ts(row['created_at'])
                    }
            except aiosqlite.Error as err:
                print(f"Select guild failed: {err}")
                return None

    async def select_all_guilds(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                async with db.execute("SELECT * FROM DiscordGuilds;") as cursor:
                    rows = await cursor.fetchall()
                    return [{**dict(row), 'created_at': self._from_ts(row['created_at'])} for row in rows]
            except aiosqlite.Error as err:
                print(f"Select all guilds failed: {err}")
                return []

    async def delete_guild(self, guild_id: int):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute("DELETE FROM DiscordGuilds WHERE guild_id=?;", (guild_id,))
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Delete guild failed: {err}")

    # --- Text Channels ---
    async def upsert_text_channel(self, channel: discord.TextChannel):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute(
                    """INSERT INTO DiscordTextChannels(channel_id, guild_id, channel_name, channel_topic, is_nsfw, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(channel_id) DO UPDATE SET
                           channel_name = EXCLUDED.channel_name,
                           channel_topic = EXCLUDED.channel_topic,
                           is_nsfw = EXCLUDED.is_nsfw;""",
                    (channel.id, channel.guild.id, channel.name, channel.topic, self._from_bool(channel.nsfw), self._to_ts(channel.created_at))
                )
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Upsert text channel failed: {err}")

    async def select_text_channel(self, guild_id: int, channel_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                async with db.execute(
                    "SELECT * FROM DiscordTextChannels WHERE guild_id=? AND channel_id=?;", (guild_id, channel_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    return {
                        **dict(row),
                        'created_at': self._from_ts(row['created_at']),
                        'is_nsfw': self._to_bool(row['is_nsfw'])
                    }
            except aiosqlite.Error as err:
                print(f"Select text channel failed: {err}")
                return None

    async def select_all_text_channels(self, guild_id: int) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                async with db.execute("SELECT * FROM DiscordTextChannels WHERE guild_id=?;", (guild_id,)) as cursor:
                    rows = await cursor.fetchall()
                    return [{**dict(row), 'created_at': self._from_ts(row['created_at']), 'is_nsfw': self._to_bool(row['is_nsfw'])} for row in rows]
            except aiosqlite.Error as err:
                print(f"Select all text channels failed: {err}")
                return []

    async def delete_text_channel(self, guild_id: int, channel_id: int):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute("DELETE FROM DiscordTextChannels WHERE guild_id=? AND channel_id=?;", (guild_id, channel_id))
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Delete text channel failed: {err}")

    # --- Messages ---
    async def upsert_message(self, message: discord.Message):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                reactions = self._json_dump([{'emoji': str(r.emoji), 'count': r.count, 'me': r.me} for r in message.reactions])
                await db.execute(
                    """INSERT INTO DiscordMessage(message_id, references_message_id, user_id, channel_id, text, reactions, created_at, edited_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(message_id) DO UPDATE SET
                           references_message_id=EXCLUDED.references_message_id,
                           text=EXCLUDED.text,
                           reactions=EXCLUDED.reactions,
                           edited_at=EXCLUDED.edited_at;""",
                    (message.id, message.reference.message_id if message.reference else None, message.author.id, message.channel.id,
                     message.content, reactions, self._to_ts(message.created_at, required=True), self._to_ts(message.edited_at))
                )
                # Upsert attachments
                for attachment in message.attachments:
                    if not attachment.ephemeral:
                        await self.upsert_attachment(db, message.id, attachment)
                await db.commit()
            except Exception as err:
                await db.rollback()
                print(f"Upsert message failed: {err}")

    async def select_message(self, message_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                async with db.execute("SELECT * FROM DiscordMessage WHERE message_id=?;", (message_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    return {**dict(row), 'created_at': self._from_ts(row['created_at']), 'edited_at': self._from_ts(row['edited_at'])}
            except aiosqlite.Error as err:
                print(f"Select message failed: {err}")
                return None

    async def delete_message(self, message_id: int):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute("DELETE FROM DiscordMessage WHERE message_id=?;", (message_id,))
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Delete message failed: {err}")

    # --- Attachments ---
    async def upsert_attachment(self, db: aiosqlite.Connection, message_id: int, attachment: discord.Attachment):
        try:
            await db.execute(
                """INSERT INTO DiscordAttachments(attachment_id, message_id, source_url, source_proxy_url, local_path, title, content_type, file_name, description, is_spoiler, size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(attachment_id) DO UPDATE SET
                       source_url=EXCLUDED.source_url,
                       source_proxy_url=EXCLUDED.source_proxy_url,
                       local_path=EXCLUDED.local_path,
                       title=EXCLUDED.title,
                       content_type=EXCLUDED.content_type,
                       file_name=EXCLUDED.file_name,
                       description=EXCLUDED.description,
                       is_spoiler=EXCLUDED.is_spoiler,
                       size=EXCLUDED.size;""",
                (attachment.id, message_id, attachment.url, attachment.proxy_url, str(path),
                 attachment.title, attachment.content_type, attachment.filename, attachment.description, attachment.is_spoiler, attachment.size)
            )
        except aiosqlite.Error as err:
            await db.rollback()
            print(f"Upsert attachment failed: {err}")

    async def select_attachment(self, attachment_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                async with db.execute("SELECT * FROM DiscordAttachments WHERE attachment_id=?;", (attachment_id,)) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
            except aiosqlite.Error as err:
                print(f"Select attachment failed: {err}")
                return None

    async def delete_attachment(self, attachment_id: int):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute("DELETE FROM DiscordAttachments WHERE attachment_id=?;", (attachment_id,))
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Delete attachment failed: {err}")

    # --- User Memory ---
    async def upsert_user_memory(self, memory: dict[str, Any]):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute(
                    """INSERT INTO UserMemory(user_id, user_name, nickname, interaction_count, last_seen_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           nickname=EXCLUDED.nickname,
                           interaction_count=EXCLUDED.interaction_count,
                           last_seen_at=EXCLUDED.last_seen_at;""",
                    (memory['user_id'], memory['user_name'], memory['nickname'], memory['interaction_count'], self._to_ts(memory['last_seen_at']))
                )
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Upsert user memory failed: {err}")

    async def select_user_memory(self, user_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                async with db.execute("SELECT * FROM UserMemory WHERE user_id=?;", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
            except aiosqlite.Error as err:
                print(f"Select user memory failed: {err}")
                return None

    async def delete_user_memory(self, user_id: int):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute("DELETE FROM UserMemory WHERE user_id=?;", (user_id,))
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Delete user memory failed: {err}")
                
    # --- Persona ---
    async def update_persona(self, persona: dict[str, Any]):
        """Update main persona record (id=1 assumed)."""
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                personality_json = self._json_dump(persona['personality_traits'])
                subject_history_json = self._json_dump(persona['subject_history'])
                await db.execute(
                    """UPDATE Persona
                    SET personality_traits=?, subject_history=?, updated_on=(strftime('%s','now'))
                    WHERE id=1;""",
                    (personality_json, subject_history_json)
                )
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Update persona failed: {err}")

    async def select_persona(self) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                async with db.execute("SELECT * FROM Persona WHERE id=1;") as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    return {
                        'personality_traits': self._json_load(row['personality_traits'], []),
                        'subject_history': self._json_load(row['subject_history'], [])
                    }
            except aiosqlite.Error as err:
                print(f"Select persona failed: {err}")
                return None

    # --- Persona Transient ---
    async def insert_persona_transient(self, entry: dict[str, Any]):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute(
                    "INSERT INTO PersonaTransient(entry, category) VALUES (?, ?);",
                    (entry['entry'], entry['category'])
                )
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Insert persona transient failed: {err}")

    async def select_persona_transient(self, category: str | None = None) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                if category:
                    async with db.execute("SELECT * FROM PersonaTransient WHERE category=?;", (category,)) as cursor:
                        rows = await cursor.fetchall()
                else:
                    async with db.execute("SELECT * FROM PersonaTransient;") as cursor:
                        rows = await cursor.fetchall()
                return [dict(row) for row in rows]
            except aiosqlite.Error as err:
                print(f"Select persona transient failed: {err}")
                return []

    async def delete_persona_transient(self, threshold_days: int):
        ts = self._to_ts(datetime.now(timezone.utc) - timedelta(days=threshold_days))
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute("DELETE FROM PersonaTransient WHERE added_on < ?;", (ts,))
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Delete persona transient failed: {err}")

    # --- User Memory Transient ---
    async def insert_memory_transient(self, memory: dict[str, Any]):
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute(
                    "INSERT INTO UserMemoryTransient(user_id, entry, category) VALUES (?, ?, ?);",
                    (memory['user_id'], memory['entry'], memory['category'])
                )
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Insert memory transient failed: {err}")

    async def select_memory_transient(self, user_id: int | None = None, category: str | None = None) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.DB_PATH) as db:
            db.row_factory = sqlite3.Row
            try:
                query = "SELECT * FROM UserMemoryTransient WHERE 1=1"
                params: list[Any] = []
                if user_id is not None:
                    query += " AND user_id=?"
                    params.append(user_id)
                if category is not None:
                    query += " AND category=?"
                    params.append(category)
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
            except aiosqlite.Error as err:
                print(f"Select memory transient failed: {err}")
                return []

    async def delete_memory_transient(self, threshold_days: int):
        ts = self._to_ts(datetime.now(timezone.utc) - timedelta(days=threshold_days))
        async with aiosqlite.connect(self.DB_PATH) as db:
            try:
                await db.execute("DELETE FROM UserMemoryTransient WHERE added_on < ?;", (ts,))
                await db.commit()
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"Delete memory transient failed: {err}")
# sqlite_dao
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional
import aiosqlite
import discord

class SQLiteDAO:
    def __init__(self):
        self.path_root = Path(__file__).resolve().parents[2]
        self.db_path = self.path_root / 'data' / 'database.db'
        self.attachments_path = self.path_root / 'data' / 'attachments'
        self.setup_script_path = self.path_root / 'setup.sqlite'

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                if self.setup_script_path.exists():
                    setup_script = self.setup_script_path.read_text()
                    if setup_script.strip():
                        await db.executescript(setup_script)
                        await db.commit()
            except aiosqlite.Error | OSError as err:
                await db.rollback()
                print(f"An error occurred during schema setup, transaction rolled back: {err}")

    # ---- Helper Methods ----

    @staticmethod
    def _json_load(value: str, default: Any) -> Any:
        """Parse JSON string, return `default` if None/invalid."""
        try:
            return json.loads(value) if value else default
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _json_dump(value: Any) -> str:
        """Serialize Python object to JSON string, empty if None."""
        return json.dumps(value) if value is not None else ""

    @staticmethod
    def _to_ts(value: datetime | None, required: bool = False) -> int | None:
        """Convert datetime to POSIX timestamp; use current UTC if required."""
        dt = value or (datetime.now(timezone.utc) if required else None)
        return int(dt.timestamp()) if dt else None

    @staticmethod
    def _from_ts(value: int | None, required: bool = False) -> datetime | None:
        """Convert POSIX timestamp to UTC datetime; use current UTC if required."""
        return datetime.fromtimestamp(value, tz=timezone.utc) if value is not None else (datetime.now(timezone.utc) if required else None)

    @staticmethod
    def _to_bool(value: int) -> bool:
        """Convert int to bool (0 -> False, others -> True)."""
        return bool(value)

    @staticmethod
    def _from_bool(value: bool) -> int:
        """Convert bool to int (False -> 0, True -> 1)."""
        return int(value)

    # ---- Discord Methods ----
    async def upsert_guild(self, guild: discord.Guild):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await self.conn.execute(
                    """INSERT INTO DiscordServers(guild_id, guild_name, guild_description, created_at) 
                    VALUES (?, ?, ?, ?) 
                    ON CONFLICT(guild_id) DO UPDATE SET
                        guild_name = EXCLUDED.guild_name,
                        guild_description = EXCLUDED.guild_description;
                    """,
                    (guild.id, guild.name, guild.description, guild.created_at)
                )
                await db.commit()
                
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"An error occurred, transaction rolled back: {err}")
                
    async def upsert_text_channel(self, channel: discord.TextChannel):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                is_nsfw = self._from_bool(channel.nsfw)
                await self.conn.execute(
                    """INSERT INTO DiscordTextChannels(channel_id, guild_id, channel_name, channel_topic, is_nsfw, created_at) 
                    VALUES (?, ?, ?, ?, ?, ?) 
                    ON CONFLICT (channel_id) DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        channel_topic = EXCLUDED.channel_topic,
                        is_nsfw = EXCLUDED.is_nsfw;
                    """,
                    (channel.id, channel.guild.id, channel.name, channel.topic, is_nsfw, channel.created_at)
                )
                
                await db.commit()
                
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"An error occurred, transaction rolled back: {err}")

    async def upsert_attachment(self, message_id: int, attachment: discord.Attachment):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                local_path = self.attachments_path / attachment.filename
                # Skip if already on disk 
                if local_path.exists(): 
                    return
                
                # Ensure directory exists
                self.attachments_path.mkdir(parents=True, exist_ok=True)

                # Save the file
                save_size = await attachment.save(use_cached=True)
                # Skip if zero bytes were downloaded (file was empty or failed to download)
                if save_size <= 0: 
                    return

                # Only update DB if save succeeds
                await self.conn.execute(
                    """INSERT INTO DiscordAttachments(
                        attachment_id, message_id, source_url, source_proxy_url, local_path,
                        title, content_type, file_name, description, is_spoiler, size
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (attachment_id) DO UPDATE SET
                        source_url = EXCLUDED.source_url,
                        source_proxy_url = EXCLUDED.source_proxy_url,
                        local_path = EXCLUDED.local_path,
                        title = EXCLUDED.title,
                        content_type = EXCLUDED.content_type,
                        file_name = EXCLUDED.file_name,
                        description = EXCLUDED.description,
                        is_spoiler = EXCLUDED.is_spoiler,
                        size = EXCLUDED.size;
                    """,
                    (
                        attachment.id,
                        message_id,
                        attachment.url,
                        attachment.proxy_url,
                        str(local_path),
                        attachment.title,
                        attachment.content_type,
                        attachment.filename,
                        attachment.description,
                        attachment.is_spoiler,
                        attachment.size
                    )
                )
                await db.commit()
                
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"An error occurred, transaction rolled back: {err}")

    async def upsert_message(self, message: discord.Message):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                reactions = self._json_dump([{'emoji': str(r.emoji), 'count': r.count, 'me': r.me} for r in message.reactions])
                references_message_id = message.reference.message_id if message.reference else None
                created_at = self._to_ts(message.created_at)
                edited_at = self._to_ts(message.edited_at)
                await self.conn.execute(
                    """INSERT INTO DiscordMessage(message_id, references_message_id, user_id, channel_id, text, reactions, created_at, edited_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?) 
                    ON CONFLICT (message_id) DO UPDATE SET
                        references_message_id = EXCLUDED.references_message_id, -- may have since been deleted
                        text = EXCLUDED.text,
                        reactions = EXCLUDED.reactions,
                        edited_at = EXCLUDED.edited_at;
                    """,
                    (message.id, 
                    references_message_id, 
                    message.author.id, 
                    message.channel.id, 
                    message.content, 
                    reactions,
                    created_at,
                    edited_at)
                )       
                await db.commit()
                
            except aiosqlite.Error as err:
                await db.rollback()
                print(f"An error occurred, transaction rolled back: {err}")
        
        for attachment in message.attachments:
            if not attachment.ephemeral: # skip if transient
                await self.upsert_attachment(message.id, attachment)
from typing import Any
import aiosqlite
from discord import ChannelType, Permissions, TextChannel
from .sqlite_dao import SQLiteDAO

class SQLiteGuildDAO(SQLiteDAO):
    @classmethod
    async def upsert_text_channel(cls, channel: TextChannel, permissions: Permissions):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                permissions_json = cls._json_dump(dict(permissions))
                await db.execute(
                    """
                    INSERT INTO DiscordTextChannels(
                        channel_id, guild_id, channel_name, channel_topic, channel_type, permissions_json, is_nsfw, created_at
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
                        channel.type.value,
                        permissions_json,
                        cls._from_bool(channel.is_nsfw),
                        cls._to_ts(channel.created_at)
                    )
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert text channel failed: {err}")
            await cls.rollback(db)
        
    @classmethod
    def _process_channel_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        row['created_at'] = cls._from_ts(row['created_at'])
        row['is_nsfw'] = cls._to_bool(row['is_nsfw'])
        row['permissions_json'] = cls._json_load(row['permissions_json'])
        row['channel_type'] = ChannelType(row['channel_type'])
        return row    
        
    @classmethod
    async def select_text_channel(cls, channel_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_one_func(
                    db, cls._process_channel_row, 
                    "SELECT * FROM DiscordTextChannels WHERE channel_id=?",
                    (channel_id,)
                )
        except aiosqlite.Error as err:
            print(f"Select text channel failed: {err}")
            return None    
        
    @classmethod
    async def select_text_channels_by_guild(cls, guild_id: int) -> list[dict[str, Any]] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_dicts(
                    db, cls._process_channel_row, 
                    "SELECT * FROM DiscordTextChannels WHERE guild_id=?", 
                    (guild_id,)
                )
        except aiosqlite.Error as err:
            print(f"Select all text channels failed: {err}")
            return None
    
    @classmethod
    async def delete_text_channel(cls, channel_id: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    "DELETE FROM DiscordTextChannels WHERE channel_id=?",
                    (channel_id,)
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete text channel failed: {err}")
            await cls.rollback(db)
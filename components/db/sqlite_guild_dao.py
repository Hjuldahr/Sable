from typing import Any
import aiosqlite
from discord import Guild, NSFWLevel, VerificationLevel

from .sqlite_dao import SQLiteDAO

class SQLiteGuildDAO(SQLiteDAO):
    @classmethod
    async def upsert_guild(cls, guild: Guild):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO DiscordGuilds(
                        guild_id, guild_name, guild_description, nsfw_level, verification_level, filesize_limit, created_at
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
                        guild.nsfw_level.value,
                        guild.verification_level.value,
                        guild.filesize_limit,
                        cls._to_ts(guild.created_at)
                    )
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert guild failed: {err}")
            await cls.rollback(db)
    
    @classmethod
    def _process_guild_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        row['nsfw_level'] = NSFWLevel(row['nsfw_level'])
        row['verification_level'] = VerificationLevel(row['verification_level'])
        row['created_at'] = cls._from_ts(row['created_at'])
        return row    
    
    @classmethod
    async def select_guild(cls, guild_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_one_func(db, cls._process_guild_row, "SELECT * FROM DiscordGuilds WHERE guild_id=?", (guild_id,))
        except aiosqlite.Error as err:
            print(f"Select guild failed: {err}")
            return None
        
    @classmethod
    async def select_all_guilds(cls) -> list[dict[str, Any]] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_func(db, cls._process_guild_row, "SELECT * FROM DiscordGuilds")
        except aiosqlite.Error as err:
            print(f"Select all guilds failed: {err}")
            return None
        
    @classmethod
    async def delete_guild(cls, guild_id: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM DiscordGuilds WHERE guild_id=?", (guild_id,))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete guild failed: {err}")
            await cls.rollback(db)
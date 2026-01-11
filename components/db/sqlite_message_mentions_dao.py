from typing import Any
import aiosqlite
from discord import Message
from .sqlite_dao import SQLiteDAO

class SQLiteMessageMentionsDAO(SQLiteDAO):
    @classmethod
    async def upsert_message_mentions(cls, message: Message):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
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
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Insert message mentions failed: {err}")
            await cls.rollback(db)
    
    @classmethod
    async def select_mentions_by_message_id(cls, message_id: int) -> list[dict[str,Any]] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                rows = await cls.fetch_all_dicts(
                    db, "SELECT * FROM DiscordMessageMentions WHERE message_id=?", (message_id,)
                )
            return rows
        except aiosqlite.Error as err:
            print(f"Select mentions failed: {err}")
            return None
    
    @classmethod
    async def delete_mentions_by_message_id(cls, message_id: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    "DELETE FROM DiscordMessageMentions WHERE message_id=?", (message_id,)
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete mentions failed: {err}")
            cls.rollback(db)
from typing import Any
import aiosqlite
from discord import Message
from .sqlite_dao import SQLiteDAO

class SQLiteMessageReactionsDAO(SQLiteDAO):
    @classmethod
    async def upsert_reactions(cls, message: Message):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
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
                            cls._json_dump([u.id async for u in r.users()])
                        )
                        for r in message.reactions
                    )
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert reactions failed: {err}")
            await cls.rollback(db)
            
    @classmethod
    def _process_reaction_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        row['users_json'] = cls._json_load(row['users_json'])
        return row          
            
    @classmethod
    async def select_reactions_by_message_id(
        cls, message_id: int
    ) -> list[dict[str, Any]] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_func(
                    db, cls._process_reaction_row,
                    "SELECT * FROM DiscordReactions WHERE message_id=?",
                    (message_id,)
                )
        except aiosqlite.Error as err:
            print(f"Select reactions failed: {err}")
            return None
        
    @classmethod
    async def delete_reactions_by_message_id(
        cls, message_id: int
    ):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    "DELETE FROM DiscordReactions WHERE message_id=?",
                    (message_id,)
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete reactions failed: {err}")
            await cls.rollback(db)
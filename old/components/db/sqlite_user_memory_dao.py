from typing import Any
import aiosqlite
from .sqlite_dao import SQLiteDAO
    
class SQLitePersonaTransientDAO(SQLiteDAO):
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
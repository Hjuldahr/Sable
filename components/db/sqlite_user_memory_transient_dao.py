from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
import aiosqlite
from .sqlite_dao import SQLiteDAO

class SQLiteUserMemoryTransientDAO(SQLiteDAO):
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
    async def insert_memories_transient(cls, memories: list[dict[str, Any]]):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.executemany(
                    """
                    INSERT INTO UserMemoryTransient(user_id, entry, category)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, entry, category) DO UPDATE SET
                        added_on=strftime('%s','now')
                    """,
                    ((memory['user_id'], memory['entry'], memory['category']) for memory in memories)
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Insert memory transient failed: {err}")
            await cls.rollback(db)

    @classmethod
    async def select_memory_transient(cls, user_id: int, category: str) -> list[dict[str, Any]] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_dicts(
                    db,
                    "SELECT * FROM UserMemoryTransient WHERE user_id=? AND category=? ORDER BY added_on",
                    (user_id, category)
                )
        except aiosqlite.Error as err:
            print(f"Select memory transient failed: {err}")
            return None 

    @classmethod
    async def select_memory_transient_category_grouped(cls, user_id: int) -> dict[str, list[dict[str, Any]]] | None:
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
            return None

    @classmethod
    async def cleanup_memory_transient(cls, threshold_days: int):
        ts = cls._to_ts(datetime.now(timezone.utc) - timedelta(days=threshold_days))
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM UserMemoryTransient WHERE added_on<?", (ts,))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete memory transient failed: {err}")
            await cls.rollback(db)
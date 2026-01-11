from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
import aiosqlite
from .sqlite_dao import SQLiteDAO

class SQLitePersonaTransientDAO(SQLiteDAO):
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
    async def select_persona_transient(cls, category: str) -> list[dict[str, Any]] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_dicts(db, "SELECT * FROM PersonaTransient WHERE category=? ORDER BY added_on", (category,))
        except aiosqlite.Error as err:
            print(f"Select persona transient failed: {err}")
            return None 
        
    @classmethod
    async def select_persona_transient_all(cls) -> dict[str,list[dict[str, Any]]] | None:
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
            return None 

    @classmethod
    async def cleanup_persona_transient(cls, threshold_days: int):
        ts = cls._to_ts(datetime.now(timezone.utc) - timedelta(days=threshold_days))
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM PersonaTransient WHERE added_on<?", (ts,))
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete persona transient failed: {err}")
            await cls.rollback(db)
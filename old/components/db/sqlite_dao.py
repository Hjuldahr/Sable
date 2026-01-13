# sqlite_dao_refactored.py
from __future__ import annotations
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3
from typing import Any
import aiosqlite
import discord
import markitdown

class SQLiteDAO:
    PATH_ROOT = Path(__file__).resolve().parents[2]
    SETUP_SCRIPT_PATH = PATH_ROOT / 'components' / 'db' / 'setup.sqlite'
    DB_PATH = PATH_ROOT / 'data' / 'sqlite' / 'database.db'
    
    MID = markitdown.MarkItDown()
    
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
    async def fetch_one_func(db: aiosqlite.Connection, func: Any, query: str, params: tuple | None = None) -> dict[str, Any] | None:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return func(dict(row)) if row else None
        
    @staticmethod
    async def fetch_one_comp(db: aiosqlite.Connection, func: Any, query: str, params: tuple | None = None) -> dict[str, Any] | None:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return await func(db, dict(row)) if row else None

    @staticmethod
    async def fetch_all_dicts(db: aiosqlite.Connection, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            return [dict(row) async for row in cursor]
        
    @staticmethod
    async def fetch_all_func(db: aiosqlite.Connection, func: Any, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            return [func(dict(row)) async for row in cursor]
        
    @staticmethod
    async def fetch_all_comp(db: aiosqlite.Connection, func: Any, query: str, params: tuple | None = None) -> list[dict[str, Any]]:
        db.row_factory = sqlite3.Row
        async with db.execute(query, params) as cursor:
            return [await func(db, dict(row)) async for row in cursor]
        
    # --- Context ---
    
    @classmethod
    async def select_context_window(
        cls,
        channel_id: int,
        limit: int = 50,
        before_ts: int | None = None
    ) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                params = [channel_id]
                where = "channel_id=?"

                if before_ts:
                    where += " AND created_at<?"
                    params.append(before_ts)

                query = f"""
                    SELECT *
                    FROM DiscordMessage
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                params.append(limit)

                rows = await cls.fetch_all_dicts(db, query, tuple(params))
                rows.reverse()  # chronological

                for row in rows:
                    row['created_at'] = cls._from_ts(row['created_at'])
                    row['edited_at'] = cls._from_ts(row['edited_at'])

                return rows
        except aiosqlite.Error as err:
            print(f"Select context window failed: {err}")
            return []

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
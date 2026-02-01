import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sqlite3
import aiosqlite
from loguru import logger

class DatabaseManager:
    PATH_ROOT = Path(__file__).resolve().parent
    DB_PATH = PATH_ROOT.parents[1] / "data" / "sqlite" / "database.db"
    SETUP_SCRIPT_PATH = PATH_ROOT / "scripts" / "setup.sqlite"
    PRAGMA_CONF_PATH = PATH_ROOT / "scripts" / "pragma.sqlite"

    # -------------------------
    # Initialization
    # -------------------------
    def __init__(self):
        self.setup_script = self.SETUP_SCRIPT_PATH.read_text()
        self.transient_pragma = self.PRAGMA_CONF_PATH.read_text()
    
    @logger.catch(Exception, reraise=True, message='Failed to initialize DB schema')
    async def _run_setup(self):
        """Run setup script as source of truth."""
        async with aiosqlite.connect(self.DB_PATH) as conn:
            await conn.executescript(self.setup_script) # WAL enabled here already

    async def async_init(self):
        """Initialize DB"""
        await self._run_setup()

    # -------------------------
    # Helpers
    # -------------------------
    @logger.catch(Exception, reraise=True, message='Failed to apply transient pragma')
    async def _apply_transient_pragma(self, conn: aiosqlite.Connection):
        await conn.executescript(self.transient_pragma)

    @staticmethod
    def _dt_to_posix(value: datetime | None) -> int | None:
        return int(value.timestamp()) if value else None

    @staticmethod
    def _posix_to_dt(value: int | None) -> datetime | None:
        return datetime.fromtimestamp(value, tz=timezone.utc) if value else None

    @staticmethod
    async def fetch_one_dict(conn: aiosqlite.Connection, query: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        conn.row_factory = sqlite3.Row
        async with conn.execute(query, params or {}) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    async def fetch_all_dicts(conn: aiosqlite.Connection, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        conn.row_factory = sqlite3.Row
        async with conn.execute(query, params or {}) as cursor:
            return [dict(row) async for row in cursor]

    @staticmethod
    async def submit(conn: aiosqlite.Connection):
        """Commit or rollback transaction safely."""
        try:
            await conn.commit()
        except Exception:
            try:
                await conn.rollback()
            except Exception as e:
                logger.exception(f"Transaction rollback failed: {e}")

    # -------------------------
    # AI Profile
    # -------------------------
    async def select_ai_profile(self) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.DB_PATH) as conn:
            return await self.fetch_one_dict(conn, "SELECT * FROM AIProfile WHERE profile_id = 1 LIMIT 1;")

    async def update_ai_profile(self, values: dict[str, Any]):
        async with aiosqlite.connect(self.DB_PATH) as conn:
            await self._apply_transient_pragma(conn)
            await conn.execute(
                """
                UPDATE AIProfile
                SET personality_traits = :personality_traits,
                    subject_history = :subject_history,
                    updated_on = strftime('%s','now')
                WHERE profile_id = 1;
                """,
                values,
            )
            await self.submit(conn)

    # -------------------------
    # User Profiles
    # -------------------------
    async def select_user_profile(self, discord_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.DB_PATH) as conn:
            return await self.fetch_one_dict(
                conn, "SELECT * FROM UserProfiles WHERE discord_id = :discord_id;",
                {"discord_id": discord_id},
            )

    async def upsert_user_profile(self, values: dict[str, Any]):
        async with aiosqlite.connect(self.DB_PATH) as conn:
            await self._apply_transient_pragma(conn)
            await conn.execute(
                """
                INSERT INTO UserProfiles(discord_id, user_name, display_name, user_to_ai_nick, ai_to_user_nick)
                VALUES (:discord_id, :user_name, :display_name, :user_to_ai_nick, :ai_to_user_nick)
                ON CONFLICT(discord_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    user_to_ai_nick = excluded.user_to_ai_nick,
                    ai_to_user_nick = excluded.ai_to_user_nick;
                """,
                values,
            )
            await self.submit(conn)

    # -------------------------
    # AI Memories
    # -------------------------
    async def insert_ai_memories(self, values: list[dict[str, Any]]):
        async with aiosqlite.connect(self.DB_PATH) as conn:
            await self._apply_transient_pragma(conn)
            await conn.executemany(
                "INSERT INTO AIMemories(entry, category) VALUES (:entry, :category);",
                values,
            )
            await self.submit(conn)

    async def insert_ai_memory(self, values: dict[str, Any]):
        await self.insert_ai_memories([values])

    async def select_all_ai_memories(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.DB_PATH) as conn:
            return await self.fetch_all_dicts(conn, "SELECT * FROM AIMemories ORDER BY added_on;")

    async def delete_old_ai_memories(self, posix_threshold: int):
        async with aiosqlite.connect(self.DB_PATH) as conn:
            await self._apply_transient_pragma(conn)
            await conn.execute(
                "DELETE FROM AIMemories WHERE added_on < :threshold;",
                {"threshold": posix_threshold},
            )
            await self.submit(conn)

    # -------------------------
    # User Memories
    # -------------------------
    async def insert_user_memories(self, values: list[dict[str, Any]]):
        async with aiosqlite.connect(self.DB_PATH) as conn:
            await self._apply_transient_pragma(conn)
            async with conn.transaction():
                await conn.execute("BEGIN")
                await conn.executemany(
                    "INSERT INTO UserMemories(user_id, entry, category) VALUES (:user_id, :entry, :category);",
                    values,
                )
                # Bulk update interaction counts
                await conn.executemany(
                    """
                    UPDATE UserProfiles
                    SET interaction_count = interaction_count + 1,
                        last_interaction_at = strftime('%s','now')
                    WHERE discord_id = :user_id;
                    """,
                    values,
                )
                await self.submit(conn)

    async def insert_user_memory(self, values: dict[str, Any]):
        async with aiosqlite.connect(self.DB_PATH) as conn:
            await self._apply_transient_pragma(conn)
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO UserMemories(user_id, entry, category) VALUES (:user_id, :entry, :category);",
                    values,
                )
                # Bulk update interaction counts
                await conn.execute(
                    """
                    UPDATE UserProfiles
                    SET interaction_count = interaction_count + 1,
                        last_interaction_at = strftime('%s','now')
                    WHERE discord_id = :user_id;
                    """,
                    values,
                )
                await self.submit(conn)

    async def select_all_user_memories(self, user_id: int) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.DB_PATH) as conn:
            return await self.fetch_all_dicts(
                conn,
                "SELECT * FROM UserMemories WHERE user_id = :user_id ORDER BY added_on;",
                {"user_id": user_id},
            )

    async def delete_old_user_memories(self, posix_threshold: int):
        async with aiosqlite.connect(self.DB_PATH) as conn:
            await self._apply_transient_pragma(conn)
            await conn.execute(
                "DELETE FROM UserMemories WHERE added_on < :threshold;",
                {"threshold": posix_threshold},
            )
        await self.submit(conn)
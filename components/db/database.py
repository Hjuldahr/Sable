import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from databases import Database
from loguru import logger

class DatabaseManager:
    DB_URL = "sqlite+aiosqlite:///./data/db/database.db"
    
    PATH_ROOT = Path(__file__).resolve().parents[2]
    SETUP_SCRIPT_PATH = PATH_ROOT / 'components' / 'db' / 'setup.sqlite'
    DB_PATH = PATH_ROOT / 'data' / 'sqlite' / 'database.db'
    
    def __init__(self):
        self.db: Database = Database(self.DB_URL)
    
    async def _async_init(self):
        await self.db.connect()
        await self.db.execute(self.SETUP_SCRIPT_PATH.read_text())
        
    async def _async_close(self):
        await self.db.disconnect()
    
    # ---- AI Profile ----
    async def select_ai_profile(self):
        row = await self.db.fetch_one("SELECT * FROM AIProfile WHERE profile_id = 1 LIMIT 1")
        return row
    
    async def update_ai_profile(self, values: dict[str, Any]):
        await self.db.execute(
            "UPDATE AIProfile SET personality_traits = :personality_traits, subject_history = :subject_history, updated_on = (strftime('%s','now')) WHERE profile_id = 1", 
            values
        )
        
    @staticmethod
    def _dt_to_posix(value: datetime | None) -> int | None:
        dt = value if value is not None else None
        return int(dt.timestamp()) if dt else None

    @staticmethod
    def _posix_to_dt(value: int | None) -> datetime | None:
        if value is not None:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return None
        
    # ---- User Profiles ----   
    async def select_user_profile(self, id):
        row = await self.db.fetch_one("SELECT * FROM UserProfiles WHERE profile_id = :profile_id")
        return row
    
    async def upsert_user_profile(self, values: dict[str, Any]):
        await self.db.execute(
            """INSERT INTO UserProfiles(discord_id, user_name, display_name, user_to_ai_nick, ai_to_user_nick) 
            VALUES(:discord_id, :user_name, :display_name, :user_to_ai_nick, :ai_to_user_nick) 
            ON CONFLICT(conflict_target_column) 
            DO UPDATE SET 
                display_name = excluded.display_name,
                user_to_ai_nick = excluded.user_to_ai_nick,
                ai_to_user_nick = excluded.ai_to_user_nick,
            """,
            values
        )
    
    # ---- AI Memories ----
    async def insert_ai_memory(self, values: dict[str, Any]):
        async with self.db.transaction():
            await self.db.execute(
                "INSERT INTO AIMemories(entry, category) VALUES (:entry, :category)", 
                values
            )
    
    async def select_all_ai_memories(self) -> list[dict]:
        async with self.db.transaction():
            rows = await self.db.fetch_all(
                "SELECT * FROM AIMemories ORDER BY added_on"
            )
        return rows
    
    async def delete_old_ai_memories(self, posix_threshold: int):
        async with self.db.transaction():
            await self.db.execute(
                "DELETE FROM AIMemories WHERE added_on < :threshold",
                {'threshold': posix_threshold}
            )
    
    # ---- User Memories ----
    async def insert_user_memory(self, values: dict[str, Any]):
        async with self.db.transaction():
            await self.db.execute(
                "INSERT INTO UserMemories(user_id, entry, category) VALUES (:user_id, :entry, :category)", 
                values
            )
            await self.db.execute(
                "UPDATE UserProfiles(user_id) VALUES SET interaction_count = interaction_count + 1, last_interaction_at = (strftime('%s','now')) WHERE user_id = :user_id", 
                values
            )
            
    async def select_all_user_memories(self, user_id) -> list[dict]:
        async with self.db.transaction():
            rows = await self.db.fetch_all(
                "SELECT * FROM UserMemories WHERE user_id = :user_id ORDER BY added_on",
                {'user_id': user_id}
            )
        return rows
            
    async def delete_old_user_memoies(self, posix_threshold: int):
        async with self.db.transaction():
            await self.db.execute(
                "DELETE FROM UserMemories WHERE added_on < :threshold", 
                {'threshold': posix_threshold}
            )
    
if __name__ == '__main__':
    test = DatabaseManager()
    asyncio.run(test.async_init())   
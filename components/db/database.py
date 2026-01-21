import asyncio
from pathlib import Path
from databases import Database
from loguru import logger

class DatabaseManager:
    DB_URL = "sqlite+aiosqlite:///./data/db/database.db"
    
    PATH_ROOT = Path(__file__).resolve().parents[2]
    PRAGMA_SCRIPT_PATH = PATH_ROOT / 'components' / 'db' / 'pragma.sqlite'
    SETUP_SCRIPT_PATH = PATH_ROOT / 'components' / 'db' / 'setup.sqlite'
    DB_PATH = PATH_ROOT / 'data' / 'sqlite' / 'database.db'
    
    def __init__(self):
        self.db: Database = Database(self.DB_URL)
    
    async def _async_init(self):
        await self.db.connect()
        await self.db.execute(self.PRAGMA_SCRIPT_PATH)
        
    async def _async_close(self):
        await self.db.disconnect()
    
    # ---- AI Profile ----
    async def select_ai_persona(self) -> dict:
        async with self.db.transaction():
            await self.db.execute('')
    
    async def update_ai_persona(self):
        pass
    
    # ---- AI Memories ----
    async def upsert_ai_memory(self):
        pass
    
    async def read_ai_memories(self) -> list[dict]:
        pass
    
    async def delete_old_ai_memories(self):
        pass
    
    # ---- User Memories ----
    
if __name__ == '__main__':
    test = DatabaseManager()
    asyncio.run(test.async_init())   
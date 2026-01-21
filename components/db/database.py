from pathlib import Path

import aiosqlite
from loguru import logger

class DatabaseManager:
    PATH_ROOT = Path(__file__).resolve().parents[2]
    PRAGMA_SCRIPT_PATH = PATH_ROOT / 'components' / 'db' / 'pragma.sqlite'
    SETUP_SCRIPT_PATH = PATH_ROOT / 'components' / 'db' / 'setup.sqlite'
    DB_PATH = PATH_ROOT / 'data' / 'sqlite' / 'database.db'
    
    db: aiosqlite.Connection = None
    
    # Call only once per application
    @classmethod
    async def async_init(cls):
        db = await cls.conn()
        await db.executescript(cls.SETUP_SCRIPT_PATH.read_text())
        await db.commit()
            
    @classmethod
    def _is_db_running(cls) -> bool:
        return getattr(cls.db, "_running", False)       
            
    @classmethod
    async def connect(cls) -> aiosqlite.Connection:
        if cls.db is None or not cls._is_db_running():
            cls.db = await aiosqlite.connect(cls.DB_PATH, timeout=10)
            await cls.db.executescript(cls.PRAGMA_SCRIPT_PATH.read_text())
            logger.info("Connected to SQLite")
            
        return cls.db
    
    @classmethod
    async def disconnect(cls):
        if cls.db is not None and cls._is_db_running():
            await cls.db.close()
            cls.db = None
            logger.info(f"Disconnected from SQLite")
        
    async def _rollback(self):
        try:
            if self.db.in_transaction:
                await self.db.rollback()
                logger.info("Transaction rollback successful")
        except Exception as e:
            logger.exception(f"Transaction rollback failed: {e}")
    
    # ---- AI Profile ----
    @classmethod
    async def select_ai_persona(cls) -> dict:
        pass
    
    @classmethod
    async def update_ai_persona(cls):
        pass
    
    # ---- AI Memories ----
    @classmethod
    async def upsert_ai_memory(cls):
        pass
    
    @classmethod
    async def read_ai_memories(cls) -> list[dict]:
        pass
    
    @classmethod
    async def delete_old_ai_memories(cls):
        pass
    
    # ---- User Memories ----
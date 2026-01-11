from typing import Any
import aiosqlite
from .sqlite_dao import SQLiteDAO

class SQLitePersonaDAO(SQLiteDAO):
    @classmethod
    async def update_persona(cls, persona: dict[str, Any]):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    """
                    UPDATE Persona
                    SET personality_traits=?, subject_history=?, updated_on=strftime('%s','now')
                    WHERE id=1
                    """,
                    (
                        cls._json_dump(persona['personality_traits']),
                        cls._json_dump(persona['subject_history'])
                    )
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Update persona failed: {err}")
            await cls.rollback(db)

    @classmethod
    def _process_persona_singleton(cls, singleton: dict[str, Any]) -> dict[str, Any]:
        singleton['personality_traits'] = cls._json_load(singleton['personality_traits'], {})
        singleton['subject_history'] = cls._json_load(singleton['subject_history'], [])
        singleton['updated_on'] = cls._from_ts(singleton['updated_on'])
        return singleton   

    @classmethod
    async def select_persona(cls) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_one_func(db, cls._process_persona_singleton, "SELECT * FROM Persona WHERE id=1")
        except aiosqlite.Error as err:
            print(f"Select persona failed: {err}")
        return None
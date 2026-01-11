from pathlib import Path
from typing import Any
import aiosqlite
from discord import Message
from .sqlite_dao import SQLiteDAO

class SQLiteMessageDAO(SQLiteDAO):
    @classmethod
    async def upsert_message(cls, message: Message, token_count: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                #reactions_json = cls._json_dump([{'emoji': str(r.emoji), 'count': r.count, 'me': r.me} for r in message.reactions])
                reference_id = (message.reference.message_id or -1) if message.reference else -1

                await db.execute(
                    """
                    INSERT INTO DiscordMessage(
                        message_id, user_id, channel_id, guild_id, 
                        content, token_count,
                        reference_message_id,
                        created_at, edited_at,
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(message_id) DO UPDATE SET
                        references_message_id=EXCLUDED.references_message_id,
                        text=EXCLUDED.text,
                        token_count=EXCLUDED.token_count,
                        reactions=EXCLUDED.reactions,
                        edited_at=EXCLUDED.edited_at
                    """,
                    (
                        message.id,
                        message.author.id,
                        message.channel.id,
                        message.guild.id,
                        message.clean_content,
                        token_count,
                        reference_id,
                        cls._to_ts(message.created_at, required=True),
                        cls._to_ts(message.edited_at)
                    )
                )
                await cls.upsert_message_mentions(message)

                for attachment in message.attachments:
                    if not attachment.ephemeral:
                        await cls.upsert_attachment(db, message.id, attachment, Path(attachment.filename))

                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert message failed: {err}")
            await cls.rollback(db)
            
    @classmethod
    async def _fetch_mentions_by_message_id(cls, db: aiosqlite.Connection, message_id: int) -> list[dict[str,Any]] | None:
        try:
            rows = await cls.fetch_all_dicts(
                db, "SELECT * FROM DiscordMessageMentions WHERE message_id=?", (message_id,)
            )
            return rows
        except aiosqlite.Error as err:
            print(f"Select mentions failed: {err}")
            return None        
            
    @classmethod
    async def _process_message_row(cls, db: aiosqlite.Connection, row: dict[str, Any]) -> dict[str, Any]:
        row['created_at'] = cls._from_ts(row['created_at'])
        row['edited_at'] = cls._from_ts(row['edited_at'])
        row['references'] = await cls._fetch_mentions_by_message_id(db, row['message_id'])
        return row            
            
    @classmethod
    async def select_message(cls, message_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_one_comp(db, cls._process_message_row, "SELECT * FROM DiscordMessage WHERE message_id=?", (message_id,))
        except aiosqlite.Error as err:
            print(f"Select message failed: {err}")
            return None
    
    @classmethod
    async def select_reply(cls, references_message_id: int) -> dict[str, Any] | None:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_one_comp(
                    db, cls._process_message_row, "SELECT * FROM DiscordMessage WHERE references_message_id=?", (references_message_id,)
                )
        except aiosqlite.Error as err:
            print(f"Select reply failed: {err}")
            return None
        
    @classmethod
    async def select_messages_by_channel(cls, channel_id: int, limit: int = -1) -> list[dict[str, Any]] | None:
        """use limit = -1 to select all rows instead of the bottom subset"""
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_comp(
                    db, cls._process_message_row,
                    f"SELECT * FROM DiscordMessage WHERE channel_id=? ORDER BY created_at DESC LIMIT {limit}",
                    (channel_id,)
                )
        except aiosqlite.Error as err:
            print(f"Select message failed: {err}")
            return None   
        
    @classmethod
    async def delete_message(cls, message_id: int):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute("DELETE FROM DiscordMessage WHERE message_id=?", (message_id,))
                await cls.delete_mentions_by_message_id(db, message_id)
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Delete message failed: {err}")
            await cls.rollback(db)    
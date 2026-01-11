from pathlib import Path
from typing import Any
import aiosqlite
from discord import Attachment, Message
from markitdown import DocumentConverterResult
from .sqlite_dao import SQLiteDAO

class SQLiteMessageAttachmentsDAO(SQLiteDAO):
    @staticmethod
    def attachments_to_tuple(attachment_data: dict[str,Message | DocumentConverterResult | Attachment | Path]) -> tuple[str | int | bool]:
        attachment: Attachment = attachment_data['attachment']
        message: Message = attachment_data['message']
        path: Path = attachment_data['path']
        markdown: DocumentConverterResult = attachment_data['markdown']

        return (
            attachment.id, message.id,
            attachment.url, attachment.proxy_url, str(path.resolve()),
            attachment.filename, attachment.content_type, attachment.size, attachment.is_spoiler,
            markdown.title, str(markdown)
        )
    
    @classmethod
    async def upsert_attachments(
        cls, attachments_data: list[dict[str,Message | DocumentConverterResult | Attachment | Path]]
    ):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.executemany(
                    """
                    INSERT INTO DiscordAttachments(
                        attachment_id, message_id,
                        source_url, source_proxy_url, local_path,
                        file_name, content_type, size, is_spoiler,
                        title, markdown
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(attachment_id) DO UPDATE SET
                        source_url=EXCLUDED.source_url,
                        source_proxy_url=EXCLUDED.source_proxy_url,
                        local_path=EXCLUDED.local_path,
                        file_name=EXCLUDED.file_name,
                        content_type=EXCLUDED.content_type,
                        size=EXCLUDED.size,
                        is_spoiler=EXCLUDED.is_spoiler,
                        title=EXCLUDED.title,
                        markdown=EXCLUDED.markdown
                    """,
                    (cls.attachments_to_tuple(attachment_data) for attachment_data in attachments_data)
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Upsert attachments failed: {err}")
            await cls.rollback(db)
            
    @classmethod
    async def select_attachments_by_message_id(
        cls, message_id: int
    ) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                return await cls.fetch_all_dicts(
                    db,
                    "SELECT * FROM DiscordAttachments WHERE message_id=?",
                    (message_id,)
                )
        except aiosqlite.Error as err:
            print(f"Failed to select attachment: {err}")
            return None
        
    @classmethod
    async def delete_attachments_by_message_id(
        cls, message_id: int
    ):
        try:
            async with aiosqlite.connect(cls.DB_PATH) as db:
                await db.execute(
                    "DELETE FROM DiscordAttachments WHERE message_id=?",
                    (message_id,)
                )
                await db.commit()
        except aiosqlite.Error as err:
            print(f"Failed to delete attachment: {err}")
            await cls.rollback(db)
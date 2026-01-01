import asyncio
from pathlib import Path
import re
from typing import Any, Dict, List

import discord
from markitdown import MarkItDown
from urlextract import URLExtract

class DiscordUtilities:
    PATH_ROOT: Path = Path(__file__).resolve().parents[2]
    ATTACHMENT_PATH: Path = PATH_ROOT / 'data' / 'discord' / 'attachments'

    MENTION_REGEX = re.compile(r'<[@#][!&]?\d{17,20}>|@everyone|@here')
    MENTION_ONLY_REGEX = re.compile(r'^(?:\s|<(?:@!|@&|@|#)\d{17,20}>|@everyone|@here)+$')

    def __init__(self):
        self.markdown = MarkItDown()
        self.extractor = URLExtract()

    async def extract_attachments_from_message(
        self, message: discord.Message
    ) -> Dict[Path, Dict[str, str | None]]:
        attachments: Dict[Path, Dict[str, str | None]] = {}

        for attachment in message.attachments:
            child_path = self.ATTACHMENT_PATH / attachment.filename
            if child_path.exists():
                continue

            try:
                await attachment.save(fp=child_path, use_cached=True)
                md = self.markdown.convert_local(child_path)
                attachments[child_path] = {
                    'title': getattr(md, 'title', None),
                    'transcription': getattr(md, 'markdown', None)
                }
            except discord.HTTPException | discord.NotFound as e:
                print(f"Error saving attachment {child_path}: {e}")

        return attachments

    async def extract_reactions_from_message(
        self, ai_user_id: int, message: discord.Message
    ) -> List[Dict[str, Any]]:
        reactions_list: List[Dict[str, Any]] = []

        for reaction in message.reactions:
            try:
                users = [user async for user in reaction.users() if user.id != ai_user_id]
                reactions_list.append({
                    'emoji': str(reaction.emoji),
                    'users': users,
                    'count': len(users)
                })
            except discord.HTTPException as e:
                print(f"Failed to extract reaction from message: {e}")
                continue

        return reactions_list

    async def extract_from_message(
        self, ai_user_id: int, message: discord.Message
    ) -> Dict[str, Any]:
        attachments, reactions = await asyncio.gather(
            self.extract_attachments_from_message(message),
            self.extract_reactions_from_message(ai_user_id, message)
        )

        return {
            'content': message.content,
            'attachments': attachments,
            'reactions': reactions,
        }

    @classmethod
    def strip_mentions(cls, text: str, repl: str = '') -> str:
        """Remove all Discord mentions from a text string."""
        return cls.MENTION_REGEX.sub(repl, text)

    @classmethod
    def is_mention_only(cls, text: str) -> bool:
        """Check if text contains only mentions or whitespace."""
        return bool(cls.MENTION_ONLY_REGEX.fullmatch(text))

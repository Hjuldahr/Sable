import asyncio
from pathlib import Path
import re
from markitdown import MarkItDown
from urlextract import URLExtract
from typing import Any, Dict, List
import discord

class DiscordUtilities:
    PATH_ROOT = Path(__file__).resolve().parents[2]
    ATTACHMENT_PATH = PATH_ROOT / 'data' / 'discord' / 'attachments'
    
    MENTION_REGEX = re.compile(r'<[@#][!&]?\d{17,20}>|@everyone|@here')
    MENTION_ONLY_REGEX = re.compile(r'^(?:\s|<(?:@!|@&|@|#)\d{17,20}>|@everyone|@here)+$')
    
    def __init__(self):
        self.markdown = MarkItDown()
        self.extractor = URLExtract()
    
    async def extract_attachments_from_message(self, message: discord.Message) -> Dict[Path, Dict[str, str]]:
        attachments = {}
        if message.attachments:
            for attachment in message.attachments:
                child_path = self.ATTACHMENT_PATHT / attachment.filename
                if child_path.exists():
                    continue
                try:
                    await attachment.save(fp=child_path, use_cached=True)
                    md = self.markdown.convert_local(child_path)
                    attachments[child_path] = {'title': md.title, 'transcription': md.markdown}
                except (discord.HTTPException, discord.NotFound) as e:
                    print(f"Error saving attachment {child_path}: {e}")
        return attachments
    
    async def extract_reactions_from_message(self, ai_user_id: int, message: discord.Message) -> List[Dict[str, Any]]:
        reactions = []
        if message.reactions:
            for reaction in message.reactions:
                try:
                    emoji = str(reaction.emoji)
                    users = [user async for user in reaction.users() if user.id != ai_user_id]
                    reactions.append({'emoji': emoji, 'users': users, 'count': len(users)})
                except discord.HTTPException as e:
                    print(f'Failed to extract reaction from message: {e}')
                    continue
        return reactions

    async def extract_from_message(
        self,
        ai_user_id: int,
        message: discord.Message
    ) -> Dict[str, Any]:

        attachments, reactions = await asyncio.gather(
            self.extract_attachments_from_message(message),
            self.extract_reactions_from_message(ai_user_id, message)
        )
        return {
            'content': message.content,
            'attachments': attachments or {},
            'reactions': reactions or [],
        }
        
    @classmethod
    def strip_mentions(cls, text: str, repl='') -> str:
        # <[@#][!&]?\d{17,20}>|@everyone|@here
        return cls.MENTION_REGEX.sub(repl, text)
    
    @classmethod
    def is_mention_only(cls, text: str) -> bool:
        # ^(?:\s|<(?:@!|@&|@|#)\d{17,20}>|@everyone|@here)+$
        return bool(cls.MENTION_ONLY_REGEX.match(text))
import asyncio
from pathlib import Path
from markitdown import MarkItDown
from urlextract import URLExtract
from typing import Any, Dict, List, Tuple
import discord

class DiscordUtilities:
    def __init__(self):
        self.markdown = MarkItDown()
        self.extractor = URLExtract()
    
    async def extract_attachments_from_message(self, parent_path: Path, message: discord.Message) -> Dict[Path, Dict[str, str]]:
        attachments = {}
        if message.attachments:
            for attachment in message.attachments:
                child_path = parent_path / attachment.filename
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
    
    async def extract_urls_from_message(self, message: discord.Message) -> Tuple[str, List[str]]:
        try:
            content = message.content
            urls = self.extractor.find_urls(content, only_unique=True, check_dns=True)
            for url in urls:
                md = self.markdown.convert_url(url) # replace with more advanced web scraper + md if needed
                content = content.replace(url, f'({url})[{md}]')
            return content, urls
        except Exception as e:
            print(f'Failed to extract URLs from message: {e}')
            return message.content, []

    async def extract_from_message(
        self,
        ai_user_id: int,
        parent_path: Path,
        message: discord.Message
    ) -> Dict[str, Any]:

        attachments, reactions, url_result = await asyncio.gather(
            self.extract_attachments_from_message(parent_path, message),
            self.extract_reactions_from_message(ai_user_id, message),
            self.extract_urls_from_message(message),
        )

        content, urls = url_result

        return {
            'content_raw': message.content,
            'content': content,
            'urls': urls or [],
            'attachments': attachments or {},
            'reactions': reactions or [],
        }
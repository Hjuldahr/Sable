import asyncio
from pathlib import Path
import re
from typing import Any, Dict, List

import discord
from markitdown import MarkItDown

class DiscordUtilities:
    PATH_ROOT: Path = Path(__file__).resolve().parents[2]
    ATTACHMENT_PATH: Path = PATH_ROOT / 'data' / 'discord' / 'attachments'
    
    MENTION_CLEANUP_REGEX = re.compile(r"([@#]\w{2,32})", re.IGNORECASE)
    MID = MarkItDown()
    
    @classmethod
    async def extract_attachments(cls, message: discord.Message):
        attachment_data: dict[str,dict[str,str]] = {}
        
        for attachment in message.attachments:
            if attachment.size == 0:
                print(f"Extract Attachments: Skipping download from {attachment.proxy_url}: Size was 0 bytes")
                continue
            
            child_path = cls.ATTACHMENT_PATH / attachment.filename
            
            if not child_path.exists():
                try:
                    bytes_written = await attachment.save(fp=child_path, use_cached=True)
                    
                    print (f"Extract Attachments: Successfully downloaded {attachment.proxy_url} to {child_path} ({attachment.size} bytes written)")
                    
                    if bytes_written == 0:
                        print(f"Extract Attachments: Skipping markdown conversion of {child_path}: Size was 0 bytes")
                        continue
                    
                    markdown = cls.MID.convert_local(child_path)
                    attachment_data[child_path] = {
                        'title': markdown.title,
                        'markdown': markdown.markdown
                    }
 
                except discord.HTTPException | discord.NotFound as e:
                    print(f"Extract Attachments: Failed attachment at {attachment.proxy_url}: {e}")
                    continue
                
        return attachment_data
    
    @classmethod
    async def extract_mentions(cls, message: discord.Message) -> tuple[Dict[int | str, discord.User | discord.Member], str]:
        mention_data: Dict[int | str, discord.User | discord.Member] = {}
        
        for mention in message.mentions:
            mention_data[mention.id] = mention
            
        clean_content = cls.MENTION_CLEANUP_REGEX.sub('', message.clean_content)
    
        return mention_data, clean_content
    
    @staticmethod
    async def extract_reactions(message: discord.Message) -> Dict[str, Dict[str, int | List[discord.Member | discord.User]]]:
        reactions_data: Dict[str, Any] = {}

        for reaction in message.reactions:
            try:
                users = [user async for user in reaction.users()]
                
                reactions_data[str(reaction.emoji)] = {
                    'users': users,
                    'count': len(users)
                }
                
            except discord.HTTPException as e:
                print(f"Failed to extract reaction from message: {e}")
                continue

        return reactions_data
    
    @staticmethod
    async def extract_references(message: discord.Message) -> dict | None:
        reference = message.reference
        
        if reference:
            return {
                'message_id': reference.message_id,
                'channel_id': reference.channel_id,
                'guild_id': reference.guild_id
            }
        else:
            return None
    
    @classmethod
    async def extract_from_message(cls, message: discord.Message):
        attachments, (mentions, clean_content), reactions, references = await asyncio.gather(
            cls.extract_attachments(message),
            cls.extract_mentions(message),
            cls.extract_reactions(message),
            cls.extract_references(message)
        )
        
        return {
            'content': clean_content,
            'attachments': attachments,
            'mentions': mentions,
            'reactions': reactions,
            'references': references
        }
from typing import Any

from components.ai.tags import Tags

class ContextBuilder:
    def __init__(self, ai_user_id: int):
        self.ai_user_id = ai_user_id

    def build(
        self,
        entries: list[dict[str, Any]],
        user_memory: dict[int, dict[str, Any]],
        channel_name: str,
    ) -> list[dict[str, Any]]:
        context = []

        for entry in entries:
            user_id = entry['user_id']
            tag_id = Tags.AI if user_id == self.ai_user_id else Tags.USER

            # Generate semantic mentions from raw mentions
            mentions = entry.get('mentions', {})
            mention_names = [user_memory[m.id]['user_name'] if m.id in user_memory else m.name for m in mentions.values()]
            semantic_mentions = ""
            if mention_names:
                semantic_mentions = "mentioning " + ", ".join(mention_names)
            if entry.get('mention_everyone') or entry.get('mention_here'):
                semantic_mentions += (", mentioning everyone" if semantic_mentions else "mentioning everyone")

            # Include reference info if present
            reference = entry.get('references')
            reference_info = None
            if reference:
                reference_info = {
                    'ref_user_name': user_memory[reference['user_id']]['user_name'] if reference['user_id'] in user_memory else "Unknown",
                    'ref_content': reference.get('content', '')
                }

            context.append({
                **entry,
                'tag_id': tag_id,
                'user_name': user_memory[user_id]['user_name'],
                'channel_name': channel_name,
                'semantic_mentions': semantic_mentions,
                'reference_info': reference_info,
            })

        return context

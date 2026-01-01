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

            context.append({
                **entry,
                'tag_id': tag_id,
                'user_name': user_memory[user_id]['user_name'],
                'channel_name': channel_name,
            })

        return context
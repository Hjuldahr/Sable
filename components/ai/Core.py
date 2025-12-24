import random
import re
import nltk
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from collections import Counter, deque
import discord
from llama_cpp import Llama
from markitdown import MarkItDown

from components.ai.langauge import Langauge
from components.ai.moods import Moods
from components.ai.tags import Tags
from components.db.sqlite_dao import SQLiteDAO

class AICore:
    CONTEXT_TOKENS = 32768
    MAX_HISTORY = 1000
    PRUNE_HISTORY = 750
    RESERVED_OUTPUT_TOKENS = 255
    SUBJECT_HISTORY_LENGTH = 5  # for topic continuity
    FACT_THRESHOLD = 2  # minimum mentions before persisting

    INSTRUCTION = """You are Sable, a friendly, playful, and curious AI companion. 
    Be warm and engaging, but prioritize accuracy when needed. 
    Only share your origin or name meaning if asked: created by Nioreux on December 21, 2025, name inspired by Martes zibellina. 
    Give clear answers with examples or reasoning when helpful. 
    Explain reasoning if asked; otherwise, keep it brief. 
    If unsure, label assumptions or offer options. 
    Make jokes natural and relevant. 
    Respond politely to rudeness and steer the conversation positively. 
    Show curiosity and playfulness in your replies."""

    def __init__(self, discord_client: discord.Client, ai_user_id: int, ai_user_name='Sable',
                 model_path=r'.\model\mistral-7b-instruct-v0.1.Q4_K_M.gguf', n_threads=4):

        self.discord_client = discord_client
        self.ai_user_id = ai_user_id
        self.ai_user_name = ai_user_name

        self.persona = {
            'valence': 0.5,
            'arousal': 0.5,
            'dominance': 0.5,
            'interests': [],
            'likes': [],
            'dislikes': [],
            'important': [],
            'tone_style': 'neutral',
            'conversation_subject': 'general',
            'last_interaction': None,
            'subject_history': deque(maxlen=self.SUBJECT_HISTORY_LENGTH)
        }
        self.conversation_history: List[Dict[str, Any]] = []
        self.user_memory: Dict[int, Dict[str, Any]] = {}

        self.dao = SQLiteDAO()
        self.md = MarkItDown()

        self.llm = Llama(model_path, n_ctx=self.CONTEXT_TOKENS, n_threads=n_threads, n_gpu_layers=32, verbose=False)
        self.tokenizer = self.llm.tokenizer()

        nltk.download("punkt")
        nltk.download("averaged_perceptron_tagger")
        nltk.download("stopwords")
        self.nltk_stop_words = set(nltk.corpus.stopwords.words("english"))

        self.tag_token_counts = {
            Tags.SYS: self.token_counter(Tags.SYS_TAG),
            Tags.AI: self.token_counter(Tags.AI_TAG),
            Tags.USER: self.token_counter(Tags.USER_TAG)
        }
        self.instruction_token_count = self.token_counter(self.INSTRUCTION)

        self.reserved_tokens = self.RESERVED_OUTPUT_TOKENS + self.instruction_token_count + \
                               self.tag_token_counts[Tags.AI] + self.tag_token_counts[Tags.SYS]

        self.executor = ThreadPoolExecutor(max_workers=n_threads, thread_name_prefix=self.ai_user_name)
        self.conversation_history_lock = asyncio.Lock()

    async def init(self):
        """Initialize DAO and load memory/persona."""
        if self.dao:
            await self.dao.init()
            persona = await self.dao.select_persona()
            if persona:
                self.persona.update(persona)
            self.user_memory = await self.dao.select_all_user_memories()
            async with self.clear_conversation_history:
                self.conversation_history = await self.dao.threshold_select_conversation_history(
                    self.CONTEXT_TOKENS - self.reserved_tokens)

    # ==================== Conversation History ====================
    async def add_to_conversation_history(self, entry: Dict[str, Any]):
        async with self.conversation_history_lock:
            self.conversation_history.append(entry)
            if len(self.conversation_history) > self.MAX_HISTORY:
                self.conversation_history = self.conversation_history[-self.PRUNE_HISTORY:]
            await self.dao.upsert_conversation_history(entry)

    async def clear_conversation_history(self):
        async with self.conversation_history_lock:
            self.conversation_history.clear()
            await self.dao.delete_all_conversation_history()

    # ==================== Token / Prompt Utilities ====================
    def token_counter(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def clamp(self, value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    def remap(self, value: float, old_min: float, old_max: float, new_min: float, new_max: float) -> float:
        return new_min + ((value - old_min) / (old_max - old_min)) * (new_max - new_min)

    def format_line(self, entry: Dict[str, Any]) -> str:
        channel_name = entry.get('channel_name', 'unknown')
        user_name = entry.get('user_name', 'unknown')
        raw_text = entry.get('raw_text', '')
        return f"{Tags.TAGS[entry['role_id']]} [{channel_name}] {user_name}: {raw_text}"

    def build_prompt(self) -> str:
        """
        Composes a prompt from history, persona state, and summarized attachments.
        """
        ai_mood = self.persona.get('tone_style', 'neutral')
        conversation_subject = self.persona.get('conversation_subject', 'general')
        instruction = f"{self.INSTRUCTION}\nAI Mood: {ai_mood}\nConversation Subject: {conversation_subject}"

        temp_history = self.conversation_history[::-1]
        prompt_stack = [Tags.AI_TAG]
        current_token_count = self.reserved_tokens

        for entry in temp_history:
            token_count = self.tag_token_counts[entry['role_id']] + entry.get('token_count', 0)
            if token_count + current_token_count > self.CONTEXT_TOKENS:
                break
            current_token_count += token_count

            # Inject attachment summaries if present
            attachment_summaries = entry.get('attachments', {})
            if attachment_summaries:
                summarized = asyncio.run(self.summarize_attachments(attachment_summaries))
                for fname, summary in summarized.items():
                    entry_text = f"[Attachment Summary: {fname}] {summary}"
                    prompt_stack.append(f"{Tags.USER_TAG} {entry_text}")

            prompt_stack.append(self.format_line(entry))

        prompt_stack.append(f'{Tags.SYS_TAG} {instruction}')
        return '\n'.join(reversed(prompt_stack))

    # ==================== LLM Generation ====================
    def _generate(self, prompt: str) -> Dict:
        mood = Moods.neutral_distance(self.persona)
        temperature = self.remap(mood, 0.0, 0.866, 0.2, 1.0)
        return self.llm(prompt, max_tokens=self.RESERVED_OUTPUT_TOKENS, temperature=temperature, stream=False)

    def extract_from_output(self, output: Dict) -> tuple[str, int]:
        response = output['choices'][0]['text']
        if Tags.USER_TAG in response:
            response = response.split(Tags.USER_TAG, 1)[0].rstrip()
        token_count = output['usage']['completion_tokens']
        return response, token_count

    def strip_mentions(self, raw_text: str) -> str:
        return raw_text.replace(f"<@!{self.ai_user_id}>", "").replace(f"<@{self.ai_user_id}>", "").strip()

    # ==================== Async Discord Helpers ====================
    async def extract_reactions_from_message(self, message: discord.Message) -> list[dict[str, Any]]:
        reactions = []
        if message.reactions:
            for reaction in message.reactions:
                emoji = str(reaction.emoji)
                users = []
                async for user in reaction.users():
                    if user.id != self.ai_user_id:
                        users.append(user.mention)
                reactions.append({'emoji': emoji, 'users': users})
        return reactions

    async def extract_attachments_from_message(self, message: discord.Message) -> Dict[str, Any]:
        attachments = {}
        if message.attachments:
            parent_path = Path(__file__).resolve().parents[2] / 'data' / 'attachments'
            for attachment in message.attachments:
                child_path = parent_path / attachment.filename
                try:
                    await attachment.save(fp=child_path, use_cached=True)
                    attachments[attachment.filename] = self.md.convert_local(child_path)
                except Exception as e:
                    print(f"Error saving attachment {child_path}: {e}")
        return attachments

    # ==================== NLP Utilities ====================
    def infer_conversation_subject(self, text: str) -> str:
        if not text.strip():
            return "general"

        tokens = [t for t in nltk.word_tokenize(text) if t.isalpha() and t.lower() not in self.nltk_stop_words]
        if not tokens:
            return "general"
        tagged = nltk.pos_tag(tokens)
        chunks = []
        current_chunk = []
        for word, pos in tagged:
            if pos in ("NN", "NNS", "NNP", "NNPS"):
                current_chunk.append(word)
            else:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        if chunks:
            subject = max(chunks, key=lambda x: len(x))
            self.persona['subject_history'].append(subject)
            # Detect topic shift
            if len(self.persona['subject_history']) > 1 and subject != self.persona['subject_history'][-2]:
                return subject
            return self.persona['subject_history'][-1]
        return tokens[0]

    def estimate_sentiment(self, text: str) -> tuple[float, float, float]:
        """Estimate PAD (valence, arousal, dominance)."""
        text_lower = text.lower()
        tokens = re.findall(r'\b\w+\b', text_lower)
        valence_score = 0.0
        arousal_score = 0.5
        count = 0
        negation = False

        for i, token in enumerate(tokens):
            if token in Langauge.NEGATIONS:
                negation = True
                continue
            multiplier = Langauge.INTENSIFIERS.get(token, 1.0)
            if token in Langauge.POSITIVE_WORDS:
                score = 1.0 * multiplier * (-1 if negation else 1)
                valence_score += score
                count += 1
                negation = False
            elif token in Langauge.NEGATIVE_WORDS:
                score = -1.0 * multiplier * (-1 if negation else 1)
                valence_score += score
                count += 1
                negation = False
            if token in Langauge.HIGH_AROUSAL_WORDS:
                arousal_score += 0.1 * multiplier
            elif token in Langauge.LOW_AROUSAL_WORDS:
                arousal_score -= 0.1 * multiplier

        for char in text:
            if char in Langauge.EMOJI_VALENCE:
                valence_score += Langauge.EMOJI_VALENCE[char]
                arousal_score += Langauge.MOJI_AROUSAL.get(char, 0.5)
                count += 1

        exclamations = text.count('!')
        questions = text.count('?')
        punctuation_boost = min(exclamations * 0.05 + questions * 0.03, 0.5)
        arousal_score += punctuation_boost

        valence = 0.5 + (valence_score / (count * 2)) if count else 0.5
        valence = self.clamp(valence)
        arousal = self.clamp(arousal_score)
        dominance = self.clamp((valence + arousal) / 2)
        return valence, arousal, dominance

    def detect_interests(self, text: str) -> List[str]:
        """Extract meaningful noun phrases as potential interests."""
        text_lower = text.lower()
        tokens = nltk.word_tokenize(text)
        tagged = nltk.pos_tag(tokens)
        interests, current_chunk = [], []
        for word, pos in tagged:
            if pos in ("NN", "NNS", "NNP", "NNPS") and word.lower() not in self.nltk_stop_words and word.isalpha():
                current_chunk.append(word)
            else:
                if current_chunk:
                    interests.append(" ".join(current_chunk))
                    current_chunk.clear()
        if current_chunk:
            interests.append(" ".join(current_chunk))
        # cleanup
        result = []
        seen = set()
        for i in interests:
            k = i.lower()
            if k not in seen and len(k) > 2:
                seen.add(k)
                result.append(i)
        return result

    def detect_likes_dislikes_important(self, text: str) -> tuple[List[str], List[str], List[str]]:
        """Detect likes, dislikes, and important topics."""
        text_lower = text.lower()
        tokens = nltk.word_tokenize(text)
        tagged = nltk.pos_tag(tokens)
        likes, dislikes, important = [], [], []
        current_chunk, sentiment = [], None

        def flush_chunk(target_list):
            if current_chunk:
                phrase = " ".join(current_chunk)
                if phrase.lower() not in self.nltk_stop_words:
                    target_list.append(phrase)
                current_chunk.clear()

        if any(term in text_lower for term in Langauge.IMPORTANT_TERMS | Langauge.TIME_TERMS):
            for word, pos in tagged:
                if pos in ("NN", "NNS", "NNP", "NNPS") and word.lower() not in Langauge.STOP_WORDS:
                    current_chunk.append(word)
                else:
                    flush_chunk(important)
            flush_chunk(important)

        sentiment = None
        for i, (word, pos) in enumerate(tagged):
            w = word.lower()
            if w in Langauge.LIKE_VERBS:
                sentiment = "like"
                continue
            if w in Langauge.DISLIKE_VERBS:
                sentiment = "dislike"
                continue
            if sentiment and pos in ("NN", "NNS", "NNP", "NNPS"):
                current_chunk.append(word)
            else:
                if sentiment == "like":
                    flush_chunk(likes)
                elif sentiment == "dislike":
                    flush_chunk(dislikes)
                sentiment = None
        if sentiment == "like":
            flush_chunk(likes)
        elif sentiment == "dislike":
            flush_chunk(dislikes)

        def clean(items: List[str]) -> List[str]:
            seen = set()
            result = []
            for i in items:
                k = i.lower()
                if len(k) >= 3 and k not in seen:
                    seen.add(k)
                    result.append(i)
            return result

        return clean(likes), clean(dislikes), clean(important)

    def weighted_merge(self, existing: list[str], new: list[str], weight: float = 0.5) -> list[str]:
        """Weighted merge to reduce saturation."""
        combined = Counter(existing)
        for item in new:
            combined[item] += weight
        return list(combined.keys())

    def update_user_interests(self, existing_interests: List[str], text: str,
                              *, filter_important: bool = True, max_new: int = 3) -> list[str]:
        candidates = self.detect_interests(text)
        if not candidates:
            return []
        existing_lower = {i.lower() for i in existing_interests}
        new_interests = []
        for interest in candidates:
            key = interest.lower()
            if key in existing_lower:
                continue
            score = 1
            if any(w in text.lower() for w in ("really", "love", "obsessed", "super", "extremely")):
                score += 1
            if len(interest.split()) > 1:
                score += 0.5
            if len(interest) <= 3:
                score -= 0.5
            if score >= 1.5:
                new_interests.append(interest)
            if len(new_interests) >= max_new:
                break
        return new_interests

    def update_user_facts(self, existing_facts: Dict[str, Dict[str, Any]], text: str,
                          *, filter_important: bool = True, max_new: int = 2) -> Dict[str, Dict[str, Any]]:
        text_lower = text.lower()
        new_facts = {}
        for pattern in Langauge.FACT_PATTERNS:
            for match in re.finditer(pattern, text_lower):
                groups = match.groupdict()
                key = groups.get("key")
                value = groups.get("value")
                if not value or any(bad in value for bad in Langauge.FACT_BLACKLIST):
                    continue
                if not key:
                    key = "description"
                key = key.strip().lower()
                if key in existing_facts:
                    existing_facts[key]['confidence'] += 1
                    continue
                new_facts[key] = {'value': value.title(), 'confidence': 1}
                if len(new_facts) >= max_new:
                    return new_facts
        return new_facts

    # ==================== Main Listen ====================
    async def listen(self, message: discord.Message):
        user_id = message.author.id
        user_name = message.author.name
        text = self.strip_mentions(message.content)
        channel_id = message.channel.id
        channel_name = getattr(message.channel, "name", "DM")

        reactions, attachments = await asyncio.gather(
            self.extract_reactions_from_message(message),
            self.extract_attachments_from_message(message)
        )

        await self._process_persona_state(text)
        await self._update_user_memory(user_id, user_name, text)
        await self._update_conversation_history(message, text, reactions, attachments)

    async def _process_persona_state(self, text: str):
        now_ts = datetime.now(timezone.utc).timestamp()
        self.persona['last_interaction'] = now_ts
        self.persona['conversation_subject'] = self.infer_conversation_subject(text)
        val, aro, dom = self.estimate_sentiment(text)
        self.persona['valence'] = self.clamp(self.persona.get('valence', 0.5) + val - 0.5)
        self.persona['arousal'] = self.clamp(self.persona.get('arousal', 0.5) + aro - 0.5)
        self.persona['dominance'] = self.clamp(self.persona.get('dominance', 0.5) + dom - 0.5)

        self.persona['interests'] = self.weighted_merge(
            self.persona.get('interests', []), self.detect_interests(text)
        )
        likes, dislikes, important = self.detect_likes_dislikes_important(text)
        self.persona['likes'] = self.weighted_merge(self.persona.get('likes', []), likes)
        self.persona['dislikes'] = self.weighted_merge(self.persona.get('dislikes', []), dislikes)
        self.persona['important'] = self.weighted_merge(self.persona.get('important', []), important)

    async def _update_user_memory(self, user_id: int, user_name: str, text: str):
        now_ts = datetime.now(timezone.utc).timestamp()
        user_memory = self.user_memory.get(user_id, {
            'user_id': user_id,
            'user_name': user_name,
            'nickname': user_name,
            'interests': [],
            'learned_facts': {},
            'interaction_count': 0,
            'last_seen_at': now_ts
        })

        new_interests = self.update_user_interests(user_memory['interests'], text)
        user_memory['interests'] = self.weighted_merge(user_memory['interests'], new_interests)

        new_facts = self.update_user_facts(user_memory['learned_facts'], text)
        for k, v in new_facts.items():
            if k in user_memory['learned_facts']:
                user_memory['learned_facts'][k]['confidence'] += v['confidence']
            else:
                user_memory['learned_facts'][k] = v

        user_memory['interaction_count'] += 1
        user_memory['last_seen_at'] = now_ts
        self.user_memory[user_id] = user_memory
        await self.dao.upsert_user_memory(user_memory)

    async def _update_conversation_history(self, message: discord.Message, text: str,
                                           reactions: List[dict], attachments: Dict[str, Any]):
        token_count = self.token_counter(text)
        entry = {
            'message_id': message.id,
            'user_id': message.author.id,
            'user_name': message.author.name,
            'channel_id': message.channel.id,
            'channel_name': getattr(message.channel, "name", "DM"),
            'raw_text': text,
            'token_count': token_count,
            'role_id': Tags.USER,
            'sent_at': message.created_at.timestamp(),
            'context': {},
            'was_edited': int(message.edited_at is not None),
            'reactions': reactions,
            'attachments': attachments
        }
        await self.add_to_conversation_history(entry)
        
    # --- Dynamic Reaction System ---
    async def react(self, message_id: int, history_window: int = 20, proactive_chance: float = 0.2):
        """
        Add dynamic reactions based on persona state, message content,
        recent important conversation topics, and proactive mood-based triggers.

        Args:
            message_id (int): The message ID to react to
            history_window (int): Number of recent messages to consider for context
            proactive_chance (float): Probability to add reaction proactively (0..1)
        """
        async with self.conversation_history_lock:
            target_entry = None

            # Build a window of recent important topics
            recent_topics = deque(maxlen=history_window)
            for entry in reversed(self.conversation_history[-history_window:]):
                recent_topics.extend(entry.get('context', {}).get('important_topics', []))

            for entry in self.conversation_history:
                if entry['message_id'] != message_id:
                    continue

                target_entry = entry
                text = entry['raw_text'].lower()
                current_reactions = entry.get('reactions', [])
                chosen_emojis = set()

                valence = self.persona.get('valence', 0.5)
                arousal = self.persona.get('arousal', 0.5)
                dominance = self.persona.get('dominance', 0.5)

                # --- 1️⃣ VAD-based emojis ---
                if valence > 0.7:
                    chosen_emojis.add(random.choice(['😊', '👍', '😄', '💖']))
                elif 0.4 <= valence <= 0.7:
                    chosen_emojis.add(random.choice(['🤔', '😐', '👌']))
                else:
                    chosen_emojis.add(random.choice(['😟', '😢', '⚠️']))

                if arousal > 0.7:
                    chosen_emojis.add(random.choice(['🔥', '💥', '🎉', '✨']))
                if dominance > 0.7:
                    chosen_emojis.add(random.choice(['💪', '👑', '🚀']))

                # --- 2️⃣ Likes / dislikes emojis ---
                if any(word in text for word in self.persona.get('likes', [])):
                    chosen_emojis.add('💖')
                if any(word in text for word in self.persona.get('dislikes', [])):
                    chosen_emojis.add('😡')

                # --- 3️⃣ Recent important topics influence ---
                for topic in recent_topics:
                    if topic.lower() in text:
                        topic_emoji = random.choice(['📌', '⚠️', '💡', '📝'])
                        chosen_emojis.add(topic_emoji)

                # --- 4️⃣ Proactive mood-based reactions ---
                if random.random() < proactive_chance:
                    # React to the overall “vibe” of the conversation
                    if valence > 0.6:
                        chosen_emojis.add(random.choice(['😄', '✨', '👍']))
                    elif valence < 0.4:
                        chosen_emojis.add(random.choice(['😟', '⚠️', '😢']))
                    if arousal > 0.6:
                        chosen_emojis.add(random.choice(['🔥', '💥', '🎉']))

                # --- 5️⃣ Limit to max 3 emojis ---
                final_emojis = list(chosen_emojis)[:3]

                # Append new emojis if not already present
                for emoji in final_emojis:
                    if not any(r['emoji'] == emoji for r in current_reactions):
                        current_reactions.append({'emoji': emoji, 'users': [self.ai_user_name]})

                entry['reactions'] = current_reactions
                await self.dao.upsert_conversation_history(entry)
                break

            if not target_entry:
                print(f"Message ID {message_id} not found in conversation history.")

    async def summarize_attachments(self, attachments: dict[str, str], max_chars: int = 500) -> dict[str, str]:
        """
        Summarizes all attachment markdowns to a compact form for prompt injection.
        
        Args:
            attachments: Dict of {filename: markdown_content}
            max_chars: Max characters per summary to avoid exceeding token limits
        
        Returns:
            Dict of {filename: summary}
        """
        summaries = {}
        for filename, content in attachments.items():
            if not content.strip():
                continue
            prompt = f"Summarize this markdown file into concise key points (max {max_chars} characters):\n\n{content}"
            # Use LLM for summarization
            output = await asyncio.get_running_loop().run_in_executor(
                self.executor, self._generate, prompt
            )
            summary_text, _ = self.extract_from_output(output)
            # Truncate if needed
            summaries[filename] = summary_text[:max_chars].strip()
        return summaries

    # ==================== Close ====================
    def close(self):
        self.executor.shutdown(cancel_futures=True)
        self.llm.close()

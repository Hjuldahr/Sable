"""
ai
"""
import re
import nltk
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import discord
from llama_cpp import Llama
from markitdown import MarkItDown

from components.ai.langauge import Langauge
from components.ai.moods import Moods
from components.ai.tags import Tags
from components.db.sqlite_dao import SQLiteDAO  # your updated DAO with reactions field

class AICore:
    """
    Central AI Core
    """
    CONTEXT_TOKENS = 32768
    MAX_HISTORY = 1000
    PRUNE_HISTORY = 750
    RESERVED_OUTPUT_TOKENS = 255

    INSTRUCTION = f"""You are Sable, a friendly, playful, and curious AI companion. 
    Be warm and engaging, but prioritize accuracy when needed. 
    Only share your origin or name meaning if asked: created by Nioreux on December 21, 2025, name inspired by Martes zibellina. 
    Give clear answers with examples or reasoning when helpful. 
    Explain reasoning if asked; otherwise, keep it brief. 
    If unsure, label assumptions or offer options. 
    Make jokes natural and relevant. 
    Respond politely to rudeness and steer the conversation positively. 
    Show curiosity and playfulness in your replies."""
    
    def __init__(
        self,
        discord_client: discord.Client,
        ai_user_id: int,
        ai_user_name='Sable',
        model_path=r'.\model\mistral-7b-instruct-v0.1.Q4_K_M.gguf',
        n_threads=4,
    ):
        """
        Args:
            discord_client (discord.Client): The client used for connection
            ai_user_id (int): The Discord Bot ID 
            ai_user_name (str, optional): The Discord Bot Username. Defaults to 'Sable'.
            model_path (str, optional): Path to the LLM model file. Defaults to r'.\model\mistral-7b-instruct-v0.1.Q4_K_M.gguf'.
            n_threads (int, optional): Multithreading Allocation. Defaults to 4.
        """
        self.discord_client = discord_client

        self.ai_user_name = ai_user_name
        self.ai_user_id = ai_user_id

        # Deferred assignment
        self.persona = {
            'valence': 0.5,
            'arousal': 0.5,
            'dominance': 0.5,
            'interests': [],
            'likes': [],
            'dislikes': [],
            'important': [],
            'tone_style': 'neutral',
            'conversation_subject': 'general'
        }
        self.conversation_history: List[Dict[str, Any]] = []
        self.user_memory: Dict[int, Dict[str, Any]] = {}

        # DAO for persistence
        self.dao = SQLiteDAO()

        # MarkItDown for file interpreting
        self.md = MarkItDown()

        # LLM
        self.llm = Llama(
            model_path,
            n_ctx=self.CONTEXT_TOKENS,
            n_threads=n_threads,
            n_gpu_layers=32,
            verbose=False
        )
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

        self.reserved_tokens = self.RESERVED_OUTPUT_TOKENS
        self.reserved_tokens += self.instruction_token_count
        self.reserved_tokens += self.tag_token_counts[Tags.AI]
        self.reserved_tokens += self.tag_token_counts[Tags.SYS]
        
        self.executor = ThreadPoolExecutor(max_workers=n_threads, thread_name_prefix=self.ai_user_name)
        
        self.conversation_history_lock = asyncio.Lock()

    async def init(self):
        """Async initialization. Calls dao init."""
        if self.dao:
            await self.dao.init()
            self.persona = await self.dao.select_persona()
            self.user_memory = await self.dao.select_all_user_memories()
            async with self.clear_conversation_history:
                self.conversation_history = await self.dao.threshold_select_conversation_history(self.CONTEXT_TOKENS - self.reserved_tokens)

    # ---- Conversation History ----
    async def add_to_conversation_history(self, entry: Dict[str, Any]):
        """
        Async conversation history update.\n
        Automatically truncates memory and persists to db.

        Args:
            entry (Dict[str, Any]): Entry to be stored
        """
        async with self.conversation_history_lock:
            self.conversation_history.append(entry)
            if len(self.conversation_history) > self.MAX_HISTORY:
                self.conversation_history = self.conversation_history[-self.PRUNE_HISTORY:]
            # Persist in DB
            await self.dao.upsert_conversation_history(entry)

    async def clear_conversation_history(self):
        """Async conversation history mass deletion."""
        async with self.conversation_history_lock:
            self.conversation_history.clear()
            await self.dao.delete_all_conversation_history()

    # ---- Formatting / Prompt Building ----
    def format_line(self, entry: Dict[str, Any]) -> str:
        """
        Formats entry for prompt injection

        Args:
            entry (Dict[str, Any]): Conversation entry data

        Returns:
            str: Formatted prompt entry
        """
        channel_name = entry.get('channel_name', 'unknown')
        user_name = entry.get('user_name', 'unknown')
        raw_text = entry.get('raw_text', '')
        return f"{Tags.TAGS[entry['role_id']]} [{channel_name}] {user_name}: {raw_text}"

    def build_prompt(self) -> str:
        """
        Composes a prompt from history and other metrics to feed into the LLM

        Returns:
            str: LLM Prompt
        """
        # Add AI mood and conversation subject indicators into instructions
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
            prompt_stack.append(self.format_line(entry))

        prompt_stack.append(f'{Tags.SYS_TAG} {instruction}')
        return '\n'.join(reversed(prompt_stack))

    def clamp(self, value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    def remap(self, value: float, old_min: float, old_max: float, new_min: float, new_max: float) -> float:
        """Linearly remap value from one range to another."""
        return new_min + ((value - old_min) / (old_max - old_min)) * (new_max - new_min)

    # ---- LLM Generation ----
    def _generate(self, prompt: str) -> Dict:
        """LLM Wrapper"""
        mood = Moods.neutral_distance(self.persona)
        temperature = self.remap(mood, 0.0, 0.866, 0.2, 1.0)
    
        return self.llm(
            prompt,
            max_tokens=self.RESERVED_OUTPUT_TOKENS,
            temperature=temperature,
            stream=False
        )

    def extract_from_output(self, output: Dict) -> tuple[str, int]:
        response = output['choices'][0]['text']
        # Remove trailing user tags if present
        if Tags.USER_TAG in response:
            response = response.split(Tags.USER_TAG, 1)[0].rstrip()
        token_count = output['usage']['completion_tokens']
        return response, token_count

    def strip_mentions(self, raw_text: str) -> str:
        """Removes Discord mention tags from text

        Args:
            raw_text (str): Original Discord message

        Returns:
            str: Cleaned message
        """
        return raw_text.replace(f'<@!{self.ai_user_id}>', '').replace(f'<@{self.ai_user_id}>', '').strip()

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
    
    async def extract_attachments_from_message(self, message: discord.Message):
        attachments = {}
        
        if message.attachments:
            parent_path = Path(__file__).resolve().parents[2] / 'data' / 'attachments'
            for attachment in message.attachments:
                child_path = parent_path / attachment.filename
                try:
                    await attachment.save(fp=child_path, use_cached=True)
                    md_text = self.md.convert_local(child_path)
                    attachments[attachment.filename] = md_text
                except Exception as e:
                    print(f'Error Encountered During Attachment Download [{child_path}]: {e}')
                    
        return attachments

    # ---- Discord Interaction ----
    async def listen(self, message: discord.Message):
        """
        Process incoming message: update history, user memory, persona state, and conversation history.

        Args:
            message (discord.Message): Message to be processed
        """
        user_id = message.author.id
        user_name = message.author.name
        text = self.strip_mentions(message.content)
        channel_id = message.channel.id
        channel_name = getattr(message.channel, 'name', 'DM')

        # Extract reactions and attachments
        reactions = await self.extract_reactions_from_message(message)
        attachments = await self.extract_attachments_from_message(message)

        # ---- Update Persona State ----
        now_ts = datetime.now(timezone.utc).timestamp()
        self.persona['last_interaction'] = now_ts
        self.persona['conversation_subject'] = self.infer_conversation_subject(text)

        # Adjust VAD (Valence, Arousal, Dominance) based on tone/content
        sentiment_shift = self.estimate_sentiment(text)  # returns tuple of (-1..1)
        self.persona['valence'] = self.clamp(self.persona.get('valence', 0.5) + sentiment_shift[0])
        self.persona['arousal'] = self.clamp(self.persona.get('arousal', 0.5) + sentiment_shift[1])
        self.persona['dominance'] = self.clamp(self.persona.get('dominance', 0.5) + sentiment_shift[2])

        # Update persona knowledge: interests, likes, dislikes, important things
        new_interests = self.detect_interests(text)
        self.persona['interests'] = list(set(self.persona.get('interests', []) + new_interests))
        
        new_likes, new_dislikes, new_important = self.detect_likes_dislikes_important(text)
        self.persona['likes'] = list(set(self.persona.get('likes', []) + new_likes))
        self.persona['dislikes'] = list(set(self.persona.get('dislikes', []) + new_dislikes))
        self.persona['important'] = list(set(self.persona.get('important', []) + new_important))

        # ---- Update User Memory ----
        user_memory = self.user_memory.get(user_id, {
            'user_id': user_id,
            'user_name': user_name,
            'nickname': user_name,
            'interests': [],
            'learned_facts': {},
            'interaction_count': 0,
            'last_seen_at': now_ts
        })

        # Update user interests/facts only if meaningful
        extracted_interests = self.update_user_interests(user_memory['interests'], text, filter_important=True)
        user_memory['interests'] = list(set(user_memory['interests'] + extracted_interests))
        
        extracted_facts = self.update_user_facts(user_memory['learned_facts'], text, filter_important=True)
        user_memory['learned_facts'].update(extracted_facts)

        user_memory['interaction_count'] += 1
        user_memory['last_seen_at'] = now_ts
        self.user_memory[user_id] = user_memory
        await self.dao.upsert_user_memory(user_memory)

        # ---- Estimate token count ----
        token_count = self.token_counter(text)

        # ---- Update Conversation History ----
        entry = {
            'message_id': message.id,
            'user_id': user_id,
            'user_name': user_name,
            'channel_id': channel_id,
            'channel_name': channel_name,
            'raw_text': text,
            'token_count': token_count,
            'role_id': Tags.USER,
            'sent_at': message.created_at.timestamp(),
            'context': {},  # can add reply-to message ID or thread context
            'was_edited': int(message.edited_at is not None),
            'reactions': reactions,
            'attachments': attachments
        }
        await self.add_to_conversation_history(entry)

    def infer_conversation_subject(self, text: str) -> str:
        """
        Lightweight NLP-based inference of conversation subject.
        Groups consecutive nouns/proper nouns into multi-word subjects.

        Args:
            text (str): Input text

        Returns:
            str: Inferred subject or 'general' if none found
        """
        if not text.strip():
            return "general"

        # Tokenize and remove stop words / non-alpha tokens
        tokens = [t for t in nltk.word_tokenize(text) if t.isalpha() and t.lower() not in self.nltk_stop_words]
        if not tokens:
            return "general"

        # POS tagging
        tagged = nltk.pos_tag(tokens)

        # Group consecutive nouns/proper nouns into chunks
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

        # Choose the longest chunk as the main subject
        if chunks:
            subject = max(chunks, key=lambda x: len(x))
            return subject

        # Fallback: first meaningful token
        return tokens[0]
    
    def estimate_sentiment(self, text: str) -> tuple[float, float, float]:
        """
        Estimates PAD (valence, arousal, dominance) from text with:
        - emojis
        - intensifiers
        - negations
        - punctuation intensity (!!, ???)
        
        Returns values between 0 and 1.
        """
        text_lower = text.lower()
        tokens = re.findall(r'\b\w+\b', text_lower)

        valence_score = 0.0
        arousal_score = 0.5  # neutral start
        count = 0
        negation = False

        for i, token in enumerate(tokens):
            # Negation handling
            if token in Langauge.NEGATIONS:
                negation = True
                continue

            # Intensifiers
            multiplier = Langauge.INTENSIFIERS.get(token, 1.0)

            # Positive / negative words
            if token in Langauge.POSITIVE_WORDS:
                score = 1.0 * multiplier
                if negation:
                    score *= -1
                valence_score += score
                count += 1
                negation = False
            elif token in Langauge.NEGATIVE_WORDS:
                score = -1.0 * multiplier
                if negation:
                    score *= -1
                valence_score += score
                count += 1
                negation = False

            # Word-based arousal
            if token in Langauge.HIGH_AROUSAL_WORDS:
                arousal_score += 0.1 * multiplier
            elif token in Langauge.LOW_AROUSAL_WORDS:
                arousal_score -= 0.1 * multiplier

        # Emoji impact
        for char in text:
            if char in Langauge.EMOJI_VALENCE:
                valence_score += Langauge.EMOJI_VALENCE[char]
                arousal_score += Langauge.MOJI_AROUSAL.get(char, 0.5)
                count += 1

        # Punctuation-based arousal (exclamation, question marks)
        exclamations = text.count('!')
        questions = text.count('?')
        punctuation_boost = min(exclamations * 0.05 + questions * 0.03, 0.5)  # cap max boost
        arousal_score += punctuation_boost

        # Normalize valence
        if count > 0:
            valence = 0.5 + (valence_score / (count * 2))  # scale -1..1 → 0..1
        else:
            valence = 0.5

        # Clamp values
        valence = max(0.0, min(1.0, valence))
        arousal = max(0.0, min(1.0, arousal_score))
        dominance = max(0.0, min(1.0, (valence + arousal) / 2))

        return valence, arousal, dominance

    def detect_interests(self, text: str) -> List[str]:
        """
        Detects meaningful user interests from text.
        Returns a list of noun phrases worth remembering.
        """

        text_lower = text.lower()
        tokens = nltk.word_tokenize(text)
        tagged = nltk.pos_tag(tokens)

        interests = []
        current_chunk = []
        confidence = 0

        # --- Step 1: Look for interest intent signals
        for verb in Moods.INTEREST_VERBS:
            if verb in text_lower:
                confidence += 1

        for intensifier in Moods.INTENSIFIERS:
            if intensifier in text_lower:
                confidence += 0.5

        # No signal → not worth remembering
        if confidence < 1:
            return []

        # --- Step 2: Extract noun / proper-noun chunks
        for word, pos in tagged:
            word_clean = word.lower()

            if (
                pos in ("NN", "NNS", "NNP", "NNPS")
                and word_clean not in self.nltk_stop_words
                and word_clean.isalpha()
            ):
                current_chunk.append(word)
            else:
                if current_chunk:
                    interests.append(" ".join(current_chunk))
                    current_chunk = []

        if current_chunk:
            interests.append(" ".join(current_chunk))

        # --- Step 3: Cleanup & normalization
        cleaned = []
        for item in interests:
            item = item.strip()
            if len(item) < 3:
                continue
            if item.lower() in self.nltk_stop_words:
                continue
            cleaned.append(item)

        # Deduplicate, preserve order
        seen = set()
        result = []
        for i in cleaned:
            key = i.lower()
            if key not in seen:
                seen.add(key)
                result.append(i)

        return result

    def detect_likes_dislikes_important(self, text: str) -> tuple[List[str], List[str], List[str]]:
        """
        Detects likes, dislikes, and important shared topics from text.

        Returns:
            (likes, dislikes, important)
        """

        text_lower = text.lower()
        tokens = nltk.word_tokenize(text)
        tagged = nltk.pos_tag(tokens)

        likes = []
        dislikes = []
        important = []

        current_chunk = []

        # --- Helper: flush noun chunk
        def flush_chunk(target_list):
            if current_chunk:
                phrase = " ".join(current_chunk)
                if phrase.lower() not in self.nltk_stop_words:
                    target_list.append(phrase)
                current_chunk.clear()

        # --- Detect IMPORTANT context (group relevance)
        if any(term in text_lower for term in Langauge.IMPORTANT_TERMS | Langauge.TIME_TERMS):
            for word, pos in tagged:
                if pos in ("NN", "NNS", "NNP", "NNPS") and word.lower() not in Langauge.STOP_WORDS:
                    current_chunk.append(word)
                else:
                    flush_chunk(important)
            flush_chunk(important)

        current_chunk.clear()

        # --- Detect LIKES / DISLIKES
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

        # Final flush
        if sentiment == "like":
            flush_chunk(likes)
        elif sentiment == "dislike":
            flush_chunk(dislikes)

        # --- Cleanup / dedupe
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

    def update_user_interests(
        self,
        existing_interests: List[str],
        text: str,
        *,
        filter_important: bool = True,
        max_new: int = 3
    ) -> list[str]:
        """
        Updates user interests based on message text.
        Returns ONLY newly accepted interests (caller merges).

        Args:
            existing_interests: Current stored interests
            text: User message
            filter_important: Require explicit interest intent
            max_new: Hard cap to avoid interest spam
        """

        # Step 1: Detect candidate interests
        candidates = self.detect_interests(text)
        if not candidates:
            return []

        existing_lower = {i.lower() for i in existing_interests}
        new_interests = []

        # Step 2: Score candidates
        for interest in candidates:
            key = interest.lower()

            # Skip if already known
            if key in existing_lower:
                continue

            score = 0

            # Explicit interest intent already detected by detect_interests
            score += 1

            # Enthusiasm boost
            if any(w in text.lower() for w in ("really", "love", "obsessed", "super", "extremely")):
                score += 1

            # Length / specificity boost
            if len(interest.split()) > 1:
                score += 0.5

            # Short or vague interests get penalized
            if len(interest) <= 3:
                score -= 0.5

            # Threshold
            if score >= 1.5:
                new_interests.append(interest)

            if len(new_interests) >= max_new:
                break

        return new_interests
    
    def update_user_facts(
        self,
        existing_facts: Dict[str, str],
        text: str,
        *,
        filter_important: bool = True,
        max_new: int = 2
    ) -> Dict[str, str]:
        """
        Extracts stable, explicit user facts from text.
        Returns ONLY newly accepted facts.

        Args:
            existing_facts: Stored facts {key: value}
            text: User message
            filter_important: Require high confidence
            max_new: Cap to prevent fact spam
        """

        text_lower = text.lower()
        new_facts = {}

        for pattern in Langauge.FACT_PATTERNS:
            for match in re.finditer(pattern, text_lower):
                groups = match.groupdict()

                key = groups.get("key")
                value = groups.get("value")

                if not value:
                    continue

                value = value.strip()

                # Reject vague / temporary states
                if any(bad in value for bad in Langauge.FACT_BLACKLIST):
                    continue

                # Normalize keys
                if key:
                    key = key.strip().lower()
                else:
                    # Infer key from pattern
                    if "work as" in match.group(0):
                        key = "profession"
                    elif "use" in match.group(0):
                        key = "tools"
                    elif "have" in match.group(0):
                        key = "has"
                    else:
                        key = "description"

                # Avoid duplicates
                if key in existing_facts:
                    continue

                # Basic confidence gate
                confidence = 1

                if any(word in text_lower for word in ("since", "for years", "always")):
                    confidence += 1

                if confidence < 1:
                    continue

                new_facts[key] = value.title()

                if len(new_facts) >= max_new:
                    return new_facts

        return new_facts

    async def response(self) -> Dict[str, Any]:
        """Generate a response using persona, user memory, and conversation history.

        Returns:
            Dict[str, Any]: Response Generated by LLM
        """
        prompt = self.build_prompt()
        output = await asyncio.get_running_loop().run_in_executor(self.executor, self._generate, prompt)
        response_text, token_count = self.extract_from_output(output)

        # Record AI message
        entry = {
            'message_id': int(datetime.now().timestamp()*1000),  # pseudo unique
            'user_id': self.ai_user_id,
            'user_name': self.ai_user_name,
            'channel_id': 0,
            'channel_name': 'AI',
            'raw_text': response_text,
            'token_count': token_count,
            'role_id': Tags.AI,
            'sent_at': datetime.now(timezone.utc).timestamp(),
            'context': {}, 
            'was_edited': 0,
            'reactions': {}
        }
        await self.add_to_conversation_history(entry)
        return {'response_text': response_text} #Include file creation and more if needed in future

    async def react(self, message_id: int):
        """Add reaction to a conversation history entry based on AI persona."""
        # TODO more dynamic reaction (not just 👍)
        # Simple heuristic: react if message has positive keywords
        async with self.conversation_history_lock:
            for entry in self.conversation_history:
                if entry['message_id'] == message_id:
                    text = entry['raw_text']
                    if any(w in text.lower() for w in ['wow', 'nice', 'good', 'great']):
                        emoji = '👍'
                        reactions = entry.get('reactions', [])
                        reactions.append({'emoji': emoji, 'users': [self.ai_user_name]})
                        entry['reactions'] = reactions
                        await self.dao.upsert_conversation_history(entry)
                    break

    # ---- Token utilities ----
    def token_counter(self, text: str) -> int:
        """
        Estimates the number of tokens that a string would consume

        Args:
            text (str): Text to be tokenized

        Returns:
            int: Quantity of tokens
        """
        return len(self.tokenizer.encode(text))

    # ---- Cleanup ----
    def close(self):
        """Terminates the LLM and its utilities"""
        self.executor.shutdown(cancel_futures=True)
        self.llm.close()
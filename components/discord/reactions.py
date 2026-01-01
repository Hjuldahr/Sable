import random
from typing import Any
import discord
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import re

from ..ai.moods import VAD

class ReactionSelector:
    SENTIMENT_EMOJI = {
        "strong_positive": ["🔥", "🤩", "🥳"],
        "mild_positive": ["🙂", "👍", "😺"],
        "neutral": ["😐", "🤔"],
        "mild_negative": ["🙁", "👎"],
        "strong_negative": ["😡", "🚫", "💀"],
    }

    TOPIC_EMOJI = {
        "code": ["💻", "🧠", "🐍"],
        "ai": ["🤖"],
        "animal": ["🐱", "🐶"],
        "food": ["🍕", "🍔"],
        "game": ["🎮"],
        "music": ["🎵"],
        "book": ["📚"],
        "math": ["📐"],
        "space": ["🌌"],
    }

    TOPIC_REGEX = {
        "code": re.compile(r"\b(code|python|js|bug|function|class|compile)\b", re.I),
        "ai": re.compile(r"\b(ai|llm|model|neural|agent)\b", re.I),
        "animal": re.compile(r"\b(cat|dog|pet|animal)\b", re.I),
        "food": re.compile(r"\b(food|pizza|burger|eat|cook)\b", re.I),
        "game": re.compile(r"\b(game|gaming|play|fps|rpg)\b", re.I),
        "music": re.compile(r"\b(music|song|guitar|piano)\b", re.I),
        "book": re.compile(r"\b(book|read|novel)\b", re.I),
        "math": re.compile(r"\b(math|algebra|geometry|equation)\b", re.I),
        "space": re.compile(r"\b(space|planet|star|galaxy)\b", re.I),
    }

    def __init__(self):
        self.sentiment = SentimentIntensityAnalyzer()

    def _vad_intensity(self, vad: VAD) -> float:
        return max(abs(vad.valence), abs(vad.arousal), abs(vad.dominance))

    def _sentiment_bucket(self, text: str, vad: VAD) -> str:
        score = self.sentiment.polarity_scores(text)["compound"]
        score *= (0.6 + self._vad_intensity(vad))

        if score > 0.6:
            return "strong_positive"
        if score > 0.15:
            return "mild_positive"
        if score < -0.6:
            return "strong_negative"
        if score < -0.15:
            return "mild_negative"
        return "neutral"

    def _detect_topic(self, text: str) -> str | None:
        for topic, rx in self.TOPIC_REGEX.items():
            if rx.search(text):
                return topic
        return None

    def _persona_match(self, text: str, persona: list[dict[str, Any]]) -> str | None:
        lowered = text.lower()
        for entry in persona:
            for cat, strength in (
                ("avoidances", "strong_negative"),
                ("dislikes", "mild_negative"),
                ("likes", "mild_positive"),
                ("passions", "strong_positive"),
            ):
                if any(k in lowered for k in entry.get(cat, [])):
                    return strength
        return None

    # Choose something that matches both the message, VAD and transient persona
    # higher intensity vad (strong valence, arousal or dominance) should also push and pull as a modifier on emoji choice (a generic response vs topical response vs quirky response)
    # if its about an AI like, do a mild positive or topical emoji (like thumbs up, or a cat for a comment about a cat)
    # if its about an AI dislike, do a mild negative emoji (thumbs down, sad, etc)
    # if its about an AI avoidance do a strong negative reaction (cancel sign, blank face, skull, etc)
    # if its an AI passion do a stronger position reaction
    # or return no reaction if it has no opinion on it

    def select_reaction(
        self,
        vad: VAD,
        transient_persona: list[dict[str, Any]],
        message: discord.Message,
    ) -> str:
        text = message.clean_content

        persona_bucket = self._persona_match(text, transient_persona)
        if persona_bucket:
            bucket = self.PERSONA_BUCKET_MAP[persona_bucket]
        else:
            bucket = self._sentiment_bucket(text, vad)

        if bucket == "neutral" and self._vad_intensity(vad) < 0.2:
            return ""

        emoji = random.choice(self.SENTIMENT_EMOJI[bucket])

        topic, confidence = self._detect_topic(text)
        if topic and confidence > 0.6 and random.random() > 0.35:
            topic_emoji = random.choice(self.TOPIC_EMOJI[topic])
            emoji = emoji + topic_emoji if self._vad_intensity(vad) > 0.6 else topic_emoji

        return emoji
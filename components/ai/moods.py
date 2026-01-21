from __future__ import annotations
import csv
from math import isclose, sqrt
from pathlib import Path
import re
from typing import Any, Iterable, SupportsFloat
import random

class VADTags:
    ANGRY = 0
    BORED = 1
    CALM = 2
    EXCITED = 3
    FEARFUL = 4
    JOYFUL = 5
    NEUTRAL = 6
    SAD = 7
    
    ANGRY_TAG = "angry"
    BORED_TAG = "bored"
    CALM_TAG = "calm"
    EXCITED_TAG = "excited"
    FEARFUL_TAG = "fearful"
    JOYFUL_TAG = "joyful"
    NEUTRAL_TAG = "neutral"
    SAD_TAG = "sad"

    MOODS = {
        NEUTRAL: NEUTRAL_TAG,
        BORED: BORED_TAG,
        CALM: CALM_TAG,
        SAD: SAD_TAG,
        FEARFUL: FEARFUL_TAG,
        ANGRY: ANGRY_TAG,
        JOYFUL: JOYFUL_TAG,
        EXCITED: EXCITED_TAG,
    }

class VAD:
    VALENCE_CATEGORY = "valence"
    AROUSAL_CATEGORY = "arousal"
    DOMINANCE_CATEGORY = "dominance"
    ATTRIBUTE_CATEGORIES = (VALENCE_CATEGORY, AROUSAL_CATEGORY, DOMINANCE_CATEGORY)
    LOW = -1.0
    HIGH = 1.0
    MAX_MAGNITUDE = sqrt(3)

    def __init__(self, valence: SupportsFloat = 0.0, arousal: SupportsFloat = 0.0, dominance: SupportsFloat = 0.0, tag: Any = None):
        self.tag = tag
        self._valence = valence
        self._arousal = arousal
        self._dominance = dominance

    @classmethod
    def _constrain(cls, value: SupportsFloat) -> float:
        return min(max(cls.LOW, float(value)), cls.HIGH)

    @property
    def valence(self) -> float:
        return self._valence

    @valence.setter
    def valence(self, valence: SupportsFloat):
        self._valence = self._constrain(valence)

    @property
    def arousal(self) -> float:
        return self._arousal

    @arousal.setter
    def arousal(self, arousal: SupportsFloat):
        self._arousal = self._constrain(arousal)

    @property
    def dominance(self) -> float:
        return self._dominance

    @dominance.setter
    def dominance(self, dominance: SupportsFloat):
        self._dominance = self._constrain(dominance)

    def __iter__(self):
        yield self._valence
        yield self._arousal
        yield self._dominance

    def to_list(self) -> list[float]:
        return list(self)

    def to_tuple(self) -> tuple[float, float, float]:
        return tuple(self)

    def to_dict(self) -> dict[str, float]:
        return dict(zip(self.ATTRIBUTE_CATEGORIES, self))

    def set_all(self, values: VAD | dict[str, float] | Iterable[float], preserve_existing: bool = True):
        if isinstance(values, dict):
            for category in self.ATTRIBUTE_CATEGORIES:
                if category in values:
                    self[category] = values[category]
                elif not preserve_existing:
                    self[category] = 0.0
        else:
            values = list(values)
            if len(values) != 3:
                raise ValueError("VAD iterable must have exactly 3 values")
            for i, value in enumerate(values):
                self[i] = value

    @staticmethod
    def distance(vad1: VAD, vad2: VAD) -> float:
        return sqrt(sum((a - b) ** 2 for a, b in zip(vad1, vad2)))

    @classmethod
    def similarity(cls, vad1: VAD, vad2: VAD) -> float:
        return 1.0 - cls.distance(vad1, vad2) / cls.MAX_MAGNITUDE

    @property
    def magnitude(self) -> float:
        return sqrt(sum(attr ** 2 for attr in self))

    @property
    def scaled_magnitude(self) -> float:
        return self.magnitude / self.MAX_MAGNITUDE

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            other_values = [other.get(k, 0.0) for k in self.ATTRIBUTE_CATEGORIES]
        elif isinstance(other, Iterable):
            other_values = list(other)
        else:
            return NotImplemented

        return all(isclose(a, b, rel_tol=1e-9, abs_tol=1e-12) for a, b in zip(self, other_values))

    def __len__(self) -> int:
        return 3

    def __getitem__(self, key: int | str) -> float:
        match key:
            case 0 | self.VALENCE_CATEGORY:
                return self.valence
            case 1 | self.AROUSAL_CATEGORY:
                return self.arousal
            case 2 | self.DOMINANCE_CATEGORY:
                return self.dominance
            case _:
                raise KeyError(f"Invalid key: {key}. Must be 0-2 or one of {self.ATTRIBUTE_CATEGORIES}")

    def __setitem__(self, key: int | str, value: float):
        match key:
            case 0 | self.VALENCE_CATEGORY:
                self.valence = value
            case 1 | self.AROUSAL_CATEGORY:
                self.arousal = value
            case 2 | self.DOMINANCE_CATEGORY:
                self.dominance = value
            case _:
                raise KeyError(f"Invalid key: {key}. Must be 0-2 or one of {self.ATTRIBUTE_CATEGORIES}")

    def __str__(self) -> str:
        return f"({self.valence:.2f}, {self.arousal:.2f}, {self.dominance:.2f})"

    def __repr__(self) -> str:
        return f"VAD(valence={self.valence:.2f}, arousal={self.arousal:.2f}, dominance={self.dominance:.2f})"

    def decay(self):
        self.valence *= random.uniform(0.91 if self.valence > 0 else 0.93, 0.95)
        self.arousal *= random.uniform(0.70, 0.85)
        self.dominance *= random.uniform(0.85, 0.90)
        
    def pertubate(self):
        self.valence += random.uniform(-0.01, 0.01)
        self.arousal += random.uniform(-0.01, 0.01)
        self.dominance += random.uniform(-0.02, 0.02) 
        
    def merge(self, other: VAD, factor: float):
        this_factor = max(0.0, 1.0 - factor)
        self.valence = self.valence * this_factor + other.valence * factor
        self.arousal = self.arousal * this_factor + other.arousal * factor  
        self.dominance = self.dominance * this_factor + other.dominance * factor
        
    def double_merge(self, other_1: VAD, factor_1: float, other_2: VAD, factor_2: float):
        this_factor = max(0.0, 1.0 - factor_1 - factor_2)
        self.valence = self.valence * this_factor + other_1.valence * factor_1 + other_2.valence * factor_2
        self.arousal = self.arousal * this_factor + other_1.arousal * factor_1 + other_2.arousal * factor_2
        self.dominance = self.dominance * this_factor + other_1.dominance * factor_1 + other_2.dominance * factor_2

class Moods:
    VADS: tuple[VAD] = (
        VAD(0.75, 0.5, 0.5, VADTags.JOYFUL),
        VAD(-0.625, 0.625, 0.625, VADTags.ANGRY),
        VAD(-0.75, 0.625, -0.625, VADTags.FEARFUL),
        VAD(-0.75, -0.625, -0.625, VADTags.SAD),
        VAD(0.5, -0.625, 0.375, VADTags.CALM),
        VAD(-0.375, -0.75, -0.375, VADTags.BORED),
        VAD(0.625, 0.875, 0.625, VADTags.EXCITED),
        VAD(0.0, 0.0, 0.0, VADTags.NEUTRAL),
    )

    @classmethod
    def ordinal(cls, n: int) -> str:
        return VADTags.MOODS.get(n, "neutral")

    @classmethod
    def ordinals(cls, ns: Iterable[int]) -> list[str]:
        return [cls.ordinal(n) for n in ns]

    @classmethod
    def calculate_mood(cls, tested_vad: VAD) -> list[tuple[int, float]]:
        results = sorted(
            ((tag_vad.tag, VAD.similarity(tested_vad, tag_vad)) for tag_vad in cls.VADS),
            key=lambda r: r[1],
            reverse=True,
        )
        return results

    @classmethod
    def next_mood(cls, vad: VAD, n: int = 3) -> int:
        results = cls.calculate_mood(vad)[:n]
        category_ids, sims = zip(*results)
        total = sum(sims)
        weights = [max(0.0, s / total) for s in sims] if total else [1.0 / len(sims)] * len(sims)
        return random.choices(category_ids, weights=weights, k=1)[0]

    @classmethod
    def tag_mood(cls, vad: VAD) -> int:
        return cls.calculate_mood(vad)[0][0]

    @classmethod
    def tag_top_n_moods(cls, vad: VAD, n: int = 3) -> list[int]:
        return [cat_id for cat_id, _ in cls.calculate_mood(vad)[:n]]

class VADWords:
    word_vad_mapping: dict[str, VAD] = {}

    # Tokenization regex
    WORD_REGEX = re.compile(r"[a-z']+", re.I)

    # Arousal affixes
    AROUSAL_PREFIX_REGEX = re.compile(r"^\.{3}")
    AROUSAL_PREFIXES = {
        "...": -0.05
    }
    AROUSAL_SUFFIX_REGEX = re.compile(r"(\.{3}|!|\?)$")
    AROUSAL_SUFFIXES = {
        "...!": 0.05,
        "...?": 0.02,
        "...": -0.02,
        "???": 0.05,
        "!!!": 0.10,
        "!?": 0.07,
        "?!": 0.07,
        "?": 0.03,
        "!": 0.06,
        ".": -0.05
    }
    SHOUTING_REGEX = re.compile(r"^(?:[^a-z]*[A-Z]+.+)+$")
    SHOUTING_OFFSET = 0.09

    # Simple negation words
    NEGATIONS = {"not", "never", "no", "n't"}

    @classmethod
    def load(cls):
        path = Path(__file__).resolve().parents[2] / 'data' / 'nrc-vad' / 'NRC-Bipolar-VAD-Lexicon.csv'
        with open(path, 'r', newline='') as file:
            reader = csv.DictReader(file)
            cls.word_vad_mapping = {row['tag']: VAD(**row) for row in reader}

    @staticmethod
    def weighted_avg(scores: list[float]) -> float:
        total_weight = sum(abs(s) for s in scores)
        return sum(s * abs(s) for s in scores) / total_weight if total_weight else 0.0

    @classmethod
    def score(cls, text: str) -> VAD:
        tokens: list[str] = cls.WORD_REGEX.findall(text)
        category_scores = [[], [], []]  # valence, arousal, dominance

        for i, token in enumerate(tokens):
            vad = cls.word_vad_mapping.get(token)
            if vad is None:
                continue

            # Check for negation within a window of 3 tokens before
            # handles both double negation and normal negation (not unhappy -> --valence -> +valence | not happy -> -valence)
            negated = any(prev in cls.NEGATIONS for prev in tokens[max(0, i - 3):i])

            # Apply negation by flipping valence
            category_scores[0].append(-vad.valence if negated else vad.valence)
            category_scores[1].append(vad.arousal)
            category_scores[2].append(vad.dominance)

        # Weighted averages per category
        category_score_averages = [
            cls.weighted_avg(scores) for scores in category_scores
        ]

        # Apply punctuation-based arousal offsets
        match = cls.AROUSAL_PREFIX_REGEX.search(text)
        if match:
            category_score_averages[1] += cls.AROUSAL_PREFIXES.get(match.group(), 0)

        match = cls.AROUSAL_SUFFIX_REGEX.search(text)
        if match:
            category_score_averages[1] += cls.AROUSAL_SUFFIXES.get(match.group(), 0)

        if cls.SHOUTING_REGEX.match(text.strip()):
            category_score_averages[1] += cls.SHOUTING_OFFSET

        vad = VAD(*category_score_averages)
        #vad.tag = Moods.tag_mood(vad)
        return vad
from __future__ import annotations
from math import isclose, sqrt
import re
from typing import Any, Iterable, Sequence
import random


class VAD:
    VALENCE_CATEGORY = "valence"
    AROUSAL_CATEGORY = "arousal"
    DOMINANCE_CATEGORY = "dominance"
    ATTRIBUTE_CATEGORIES = (VALENCE_CATEGORY, AROUSAL_CATEGORY, DOMINANCE_CATEGORY)
    LOW = -1.0
    HIGH = 1.0
    MAX_MAGNITUDE = sqrt(3)

    def __init__(self, category_id: int = -1, valence: float = 0.0, arousal: float = 0.0, dominance: float = 0.0):
        self.category_id = category_id
        self._valence = valence
        self._arousal = arousal
        self._dominance = dominance

    @classmethod
    def _constrain(cls, value: float) -> float:
        if not isinstance(value, (int, float)):
            raise TypeError(f"Invalid Datatype: {value}. Must be int or float.")
        return min(max(cls.LOW, value), cls.HIGH)

    @property
    def valence(self) -> float:
        return self._valence

    @valence.setter
    def valence(self, valence: float):
        self._valence = self._constrain(valence)

    @property
    def arousal(self) -> float:
        return self._arousal

    @arousal.setter
    def arousal(self, arousal: float):
        self._arousal = self._constrain(arousal)

    @property
    def dominance(self) -> float:
        return self._dominance

    @dominance.setter
    def dominance(self, dominance: float):
        self._dominance = self._constrain(dominance)

    def __iter__(self):
        yield self.valence
        yield self.arousal
        yield self.dominance

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

class Moods:
    ANGRY = 0
    BORED = 1
    CALM = 2
    EXCITED = 3
    FEARFUL = 4
    JOYFUL = 5
    NEUTRAL = 6
    SAD = 7

    MOODS = {
        NEUTRAL: "neutral",
        BORED: "bored",
        CALM: "calm",
        SAD: "sad",
        FEARFUL: "fearful",
        ANGRY: "angry",
        JOYFUL: "joyful",
        EXCITED: "excited",
    }

    VADS: tuple[VAD, ...] = (
        VAD(JOYFUL, 0.75, 0.5, 0.5),
        VAD(ANGRY, -0.625, 0.625, 0.625),
        VAD(FEARFUL, -0.75, 0.625, -0.625),
        VAD(SAD, -0.75, -0.625, -0.625),
        VAD(CALM, 0.5, -0.625, 0.375),
        VAD(BORED, -0.375, -0.75, -0.375),
        VAD(EXCITED, 0.625, 0.875, 0.625),
        VAD(NEUTRAL, 0.0, 0.0, 0.0),
    )

    @classmethod
    def ordinal(cls, n: int) -> str:
        return cls.MOODS.get(n, "neutral")

    @classmethod
    def ordinals(cls, ns: Iterable[int]) -> list[str]:
        return [cls.ordinal(n) for n in ns]

    @classmethod
    def calculate_mood(cls, tested_vad: VAD) -> list[tuple[int, float]]:
        results = sorted(
            ((label_vad.category_id, VAD.similarity(tested_vad, label_vad)) for label_vad in cls.VADS),
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
    def label_mood(cls, vad: VAD) -> int:
        return cls.calculate_mood(vad)[0][0]

    @classmethod
    def label_top_n_moods(cls, vad: VAD, n: int = 3) -> list[int]:
        return [cat_id for cat_id, _ in cls.calculate_mood(vad)[:n]]

class VADWords:
    VALENCE_MAP = {
        "love": 0.7,
        "awesome": 0.8,
        "adore": 0.9,
        "like": 0.5,
        "yay": 0.6,
        "hate": -0.7,
        "awful": -0.8,
        "loathe": -0.9,
        "dislike": -0.5,
        "ugh": -0.6
    }

    AROUSAL_MAP = {
        "!": 0.5,
        "!?": 0.75,
        "!!": 0.8,
        "?!": 0.7,
        "?": 0.25,
        "...": -0.05
    }

    DOMINANCE_MAP = {
        "please": -0.2,
        "mandatory": 0.4,
        "required": 0.35,
        "must": 0.3,
        "could": 0.1,
        "perhaps": -0.1,
        "can't": -0.3,
        "should": 0.2
    }

    @classmethod
    def score_valence(cls, text: str) -> float:
        text_lower = text.lower()
        valence_scores = [score for word, score in cls.VALENCE_MAP.items() if word in text_lower]
        if not valence_scores:
            return 0.0
        # average, weighted toward stronger words
        return sum(valence_scores) / len(valence_scores)

    @classmethod
    def score_arousal(cls, text: str) -> float:
        # pick the strongest matching arousal cue from punctuation
        text = text.strip()
        scores = []
        for ending, score in cls.AROUSAL_MAP.items():
            pattern = re.escape(ending) + r'$'  # match at the end
            if re.search(pattern, text):
                scores.append(score)
        return max(scores) if scores else 0.0

    @classmethod
    def score_dominance(cls, text: str) -> float:
        text_lower = text.lower()
        dom_scores = [score for word, score in cls.DOMINANCE_MAP.items() if word in text_lower]
        return sum(dom_scores) if dom_scores else 0.0

    @classmethod
    def score(cls, text: str) -> VAD:
        new_vad = VAD(
            valence=cls.score_valence(text),
            arousal=cls.score_arousal(text),
            dominance=cls.score_dominance(text)
        )
        new_vad.category_id = Moods.label_mood(new_vad)
        return new_vad
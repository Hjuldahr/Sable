from __future__ import annotations
from collections import defaultdict
import csv
from math import isclose, sqrt
from pathlib import Path
import re
from typing import Any, Iterable, Sequence, SupportsFloat
import random

class VAD:
    VALENCE_CATEGORY = "valence"
    AROUSAL_CATEGORY = "arousal"
    DOMINANCE_CATEGORY = "dominance"
    ATTRIBUTE_CATEGORIES = (VALENCE_CATEGORY, AROUSAL_CATEGORY, DOMINANCE_CATEGORY)
    LOW = -1.0
    HIGH = 1.0
    MAX_MAGNITUDE = sqrt(3)

    def __init__(self, valence: SupportsFloat = 0.0, arousal: SupportsFloat = 0.0, dominance: SupportsFloat = 0.0, label: Any = None):
        self.label = label
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

    VADS: tuple[VAD] = (
        VAD(0.75, 0.5, 0.5, JOYFUL),
        VAD(-0.625, 0.625, 0.625, ANGRY),
        VAD(-0.75, 0.625, -0.625, FEARFUL),
        VAD(-0.75, -0.625, -0.625, SAD),
        VAD(0.5, -0.625, 0.375, CALM),
        VAD(-0.375, -0.75, -0.375, BORED),
        VAD(0.625, 0.875, 0.625, EXCITED),
        VAD(0.0, 0.0, 0.0, NEUTRAL),
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
            ((label_vad.label, VAD.similarity(tested_vad, label_vad)) for label_vad in cls.VADS),
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
    word_vad_mapping: dict[str, VAD] = {}

    WORD_RE = re.compile(r"[a-z']+")

    # Optional punctuation-based arousal cues
    AROUSAL_OVERRIDES = {
        "!!": 0.8,
        "!?": 0.75,
        "?!": 0.7,
        "!": 0.5,
        "?": 0.25,
        "...": -0.05,
    }
    # Pre-sort endings by length so longer ones match first
    AROUSAL_ENDINGS = tuple(sorted(AROUSAL_OVERRIDES, key=len, reverse=True))

    @classmethod
    def load(cls, path: Path):
        import csv
        with open(path, 'r', newline='') as file:
            reader = csv.DictReader(file)
            cls.word_vad_mapping = {row['label']: VAD(**row) for row in reader}

    @staticmethod
    def weighted_avg(scores: list[float]) -> float:
        total_weight = sum(abs(s) for s in scores)
        return sum(s * abs(s) for s in scores) / total_weight if total_weight else 0.0

    @classmethod
    def score(cls, text: str) -> VAD:
        text_l = text.lower()
        tokens: list[str] = cls.WORD_RE.findall(text_l)
        category_scores = [[],[],[]]

        # Lookup VAD for each token
        for token in tokens:
            vad = cls.word_vad_mapping.get(token)
            if vad is not None:
                category_scores[0].append(vad.valence)
                category_scores[1].append(vad.arousal)
                category_scores[2].append(vad.dominance)

        # Compute weighted averages
        category_score_averages = [
            cls.weighted_avg(scores)
            for scores in category_scores
        ]

        # Apply punctuation-based arousal override (highest matching)
        stripped_text = text.rstrip()
        for ending in cls.AROUSAL_ENDINGS:
            if stripped_text.endswith(ending):
                category_score_averages[1] = cls.AROUSAL_OVERRIDES[ending]
                break

        vad = VAD(*category_score_averages)
        vad.label = Moods.label_mood(vad)
        return vad
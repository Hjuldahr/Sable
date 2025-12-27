from __future__ import annotations
from math import isclose, sqrt
from typing import Any, Iterable
import random

class VAD:
    VALENCE_CATEGORY = 'valence'
    AROUSAL_CATEGORY = 'arousal'
    DOMINANCE_CATEGORY = 'dominance'
    ATTRIBUTE_CATEGORIES = (VALENCE_CATEGORY, AROUSAL_CATEGORY , DOMINANCE_CATEGORY)
    LOW = -1.0
    HIGH = 1.0
    MAX_MAGNITUDE = sqrt(3)
    
    def __init__(self, category_id:int, valence:float=0.0, arousal:float=0.0, dominance:float=0.0):
        self.category_id = category_id
        self._valence = valence
        self._arousal = arousal
        self._dominance = dominance
        
    @classmethod
    def _constrain(cls, value: float):
        if not isinstance(value, (int, float)):
            raise TypeError(f"Invalid Datatype: {value}. Must be of dtype integer or float.")
        return min(max(cls._LOW, value), cls._HIGH)    
        
    @property
    def valence(self):
        return self._valence
    
    @valence.setter
    def valence(self, valence: float):
        self._valence = self._constrain(valence)
    
    @property
    def arousal(self):
        return self._arousal
    
    @arousal.setter
    def arousal(self, arousal: float):
        self._arousal = self._constrain(arousal)
        
    @property
    def dominance(self):
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
        return sqrt(sum((attr2 - attr1) ** 2 for attr1, attr2 in zip(vad1, vad2)))
     
    @classmethod
    def similarity(cls, vad1: VAD, vad2: VAD) -> float:
        return 1.0 - (cls.distance(vad1, vad2) / cls._MAX_MAGNITUDE)
        
    @property
    def magnitude(self) -> float:
        return sqrt(sum(attr ** 2 for attr in self))
    
    @property
    def scaled_magnitude(self) -> float:
        return self.magnitude / self._MAX_MAGNITUDE
    
    def __eq__(self, other: Any):
        if not isinstance(other, (VAD, dict, Iterable)):
            return NotImplemented
        if isinstance(other, dict):
            other_values = [other.get(k, 0.0) for k in self.ATTRIBUTE_CATEGORIES]
        else:
            other_values = list(other)
        return all(
            isclose(v1, v2, rel_tol=1e-09, abs_tol=1e-12) 
            for v1, v2 in zip(self, other_values)
        )
    
    def __len__(self) -> int:
        return 3
    
    def __getitem__(self, key: int | str) -> float:
        match(key):
            case 0 | self.VALENCE_CATEGORY:
                return self.valence
            case 1 | self.AROUSAL_CATEGORY:
                return self.arousal
            case 2 | self.DOMINANCE_CATEGORY:
                return self.dominance
            case _:
                raise KeyError(f'Invalid Key: {key}. Must be an integer between [0,3), or match one of {self.ATTRIBUTE_CATEGORIES}')
    
    def __setitem__(self, key: int | str, value: float):
        match(key):
            case 0 | self.VALENCE_CATEGORY:
                self.valence = value
            case 1 | self.AROUSAL_CATEGORY:
                self.arousal = value
            case 2 | self.DOMINANCE_CATEGORY:
                self.dominance = value
            case _:
                raise KeyError(f'Invalid Key: {key}. Must be an integer between [0,3), or match one of {self.ATTRIBUTE_CATEGORIES}')
    
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
    
    JOYFUL_MOOD = 'joyful'
    ANGRY_MOOD = 'angry'
    FEARFUL_MOOD = 'fearful'
    SAD_MOOD = 'sad'
    CALM_MOOD = 'calm'
    BORED_MOOD = 'bored'
    EXCITED_MOOD = 'excited'
    NEUTRAL_MOOD = 'neutral'
    
    MOODS = {
        NEUTRAL: NEUTRAL_MOOD, 
        BORED: BORED_MOOD,
        CALM: CALM_MOOD,
        SAD: SAD_MOOD,
        FEARFUL: FEARFUL_MOOD,
        ANGRY: ANGRY_MOOD,
        JOYFUL: JOYFUL_MOOD,
        EXCITED: EXCITED_MOOD
    }
    
    VADS = (
        VAD(JOYFUL,   0.75,   0.50,   0.50), 
        VAD(ANGRY,   -0.625,  0.625,  0.625),
        VAD(FEARFUL, -0.75,   0.625, -0.625),
        VAD(SAD,     -0.75,  -0.625, -0.625),
        VAD(CALM,     0.5,   -0.625,  0.375),
        VAD(BORED,   -0.375, -0.75,  -0.375),
        VAD(EXCITED,  0.625,  0.875,  0.625),
        VAD(NEUTRAL,  0,      0,      0) 
    )
    
    @classmethod
    def ordinal(cls, n: int) -> str:
        return cls.MOODS.get(n)
    
    @classmethod
    def ordinals(cls, ns: Iterable[int]) -> list[str]:
        return [cls.ordinal(n) for n in ns]

    @classmethod
    def calculate_mood(cls, tested_vad: VAD) -> list[tuple[int, float]]:
        results = sorted(
            ((label_vad.category_id, VAD.similarity(tested_vad, label_vad)) for label_vad in cls.VADS), 
            key=lambda r: r[1], reverse=True
        )
        return results

    @classmethod
    def next_mood(cls, vad: VAD, n: int = 3) -> int:
        results = cls.calculate_mood(vad)[:n]
        category_ids, sims = zip(results)
        total = sum(sims)
        return random.choices(category_ids, weights=[max(0.0, v / total) for v in sims], k=1)[0]

    @classmethod
    def label_mood(cls, vad: VAD) -> int:
        return cls.calculate_mood(vad)[0]

    @classmethod
    def label_top_n_moods(cls, vad: VAD, n: int = 3) -> list[int]:
        return cls.calculate_mood(vad)[:n]
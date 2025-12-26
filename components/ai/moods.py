from __future__ import annotations
from math import isclose, sqrt
from typing import Any, Iterable

class VAD:
    VALENCE = 'valence'
    AROUSAL = 'arousal'
    DOMINANCE = 'dominance'
    ATTR_NAMES = (VALENCE, AROUSAL, DOMINANCE)
    
    def __init__(self, valence=0.5, arousal=0.5, dominance=0.5):
        self.valence = valence
        self.arousal = arousal
        self.dominance = dominance
        
    def __iter__(self):
        return (getattr(self, attr) for attr in self.ATTR_NAMES)
    
    def to_list(self) -> list[float]:
        return list(self)
    
    def to_tuple(self) -> tuple[float, float, float]:
        return tuple(self)
    
    def to_dict(self) -> dict[str, float]:
        return dict(zip(self.ATTR_NAMES, self))
    
    def from_dict(self, values: dict[str, float], preserve_existing: bool = True):
        for k in self.ATTR_NAMES:
            if k in values:
                setattr(self, k, max(0.0, min(1.0, values[k])))
            elif preserve_existing:
                setattr(self, k, getattr(self, k, 0.5))
                
    def set_all(self, values: 'VAD | dict[str, float] | Iterable[float]'):
        if isinstance(values, dict):
            for k in self.ATTR_NAMES:
                setattr(self, k, max(0.0, min(1.0, values.get(k, 0.5))))
        else:
            for k, v in zip(self.ATTR_NAMES, values):
                setattr(self, k, max(0.0, min(1.0, v)))
    
    def blend(self, other: 'VAD', weight: float = 0.5) -> 'VAD':
        """Blend another VAD into this one, weight = influence of `other` (0..1)."""
        return VAD(*(self[i] * (1 - weight) + other[i] * weight for i in range(3)))
    
    def __eq__(self, other: Any):
        if not isinstance(other, (VAD, dict, Iterable)):
            return NotImplemented
        if isinstance(other, dict):
            other_values = [other.get(k, 0.5) for k in self.ATTR_NAMES]
        else:
            other_values = list(other)
        return all(
            isclose(v1, v2, rel_tol=1e-09, abs_tol=1e-12) 
            for v1, v2 in zip(self, other_values)
        )
    
    def __len__(self) -> int:
        return len(self.ATTR_NAMES)
    
    def __getitem__(self, key: int | str) -> float:
        if isinstance(key, int):
            key = self.ATTR_NAMES[key]
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(f"Invalid key: {key}. Must be one of {self.ATTR_NAMES}")
    
    def __setitem__(self, key: int | str, value: float):
        if isinstance(key, int):
            key = self.ATTR_NAMES[key]
        if key in self.ATTR_NAMES:
            setattr(self, key, max(0.0, min(1.0, value)))
        else:
            raise KeyError(f"Cannot set attribute: {key}")
    
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
    
    VAD = {
        JOYFUL: {'valence': 0.8, 'arousal':0.7, 'dominance':0.7}, 
        ANGRY: {'valence': 0.2, 'arousal':0.7, 'dominance':0.7}, 
        FEARFUL: {'valence': 0.1, 'arousal':0.7, 'dominance':0.2}, 
        SAD: {'valence': 0.1, 'arousal':0.2, 'dominance':0.2}, 
        CALM: {'valence': 0.7, 'arousal':0.2, 'dominance':0.6}, 
        BORED: {'valence': 0.3, 'arousal':0.1, 'dominance':0.3}, 
        EXCITED: {'valence': 0.7, 'arousal':0.8, 'dominance':0.7}, 
        NEUTRAL: {'valence': 0.5, 'arousal':0.5, 'dominance':0.5}, 
    }
    
    @classmethod
    def ordinal(cls, n: int) -> str:
        return cls.MOODS.get(n)
    
    @classmethod
    def ordinals(cls, ns: Iterable[int]) -> list[str]:
        return [cls.ordinal(n) for n in ns]
    
    @classmethod
    def neutral_distance(cls, vad: dict[str, float]) -> float:
        return cls.distance(Moods.VAD[Moods.NEUTRAL], vad)
    
    @staticmethod
    def distance(vad1: dict[str, float], vad2: dict[str, float]) -> float:
        return sqrt(
            (vad2['valence'] - vad1['valence']) ** 2 +
            (vad2['arousal'] - vad1['arousal']) ** 2 +
            (vad2['dominance'] - vad1['dominance']) ** 2
        )
    
    @classmethod
    def calculate_mood(cls, valence: float, arousal: float, dominance: float) -> dict[int, float]:
        input_vad = {'valence': valence, 'arousal': arousal, 'dominance': dominance}
        results = {
            mood: cls.distance(input_vad, output_vad) 
            for mood, output_vad in cls.VAD.items()
        }
        return results
    
    @staticmethod
    def top_mood(results: dict[int, float]) -> int:
        return min(results, key=results.get)
    
    @classmethod
    def get_top_mood(cls, valence: float, arousal: float, dominance: float) -> int:
        results = cls.calculate_mood(valence, arousal, dominance)
        return cls.top_mood(results)
    
    @staticmethod
    def top_n_moods(results: dict[int, float], n: int = 3) -> list[int]:
        return sorted(results, key=results.get)[:n]
    
    @classmethod
    def get_top_n_mood(cls, valence: float, arousal: float, dominance: float, n: int = 3) -> list[int]:
        results = cls.calculate_mood(valence, arousal, dominance)
        return cls.top_n_moods(results, n)

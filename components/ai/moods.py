import math
from typing import Iterable

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
        return math.sqrt(
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

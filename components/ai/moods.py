import math

class Moods:
    JOYFUL_MOOD = 'joyful'
    ANGRY_MOOD = 'angry'
    FEARFUL_MOOD = 'fearful'
    SAD_MOOD = 'sad'
    CALM_MOOD = 'calm'
    BORED_MOOD = 'bored'
    EXCITED_MOOD = 'excited'
    NEUTRAL_MOOD = 'neutral'
    
    VAD = {
        JOYFUL_MOOD: {'valence': 0.8, 'arousal':0.7, 'dominance':0.7}, 
        ANGRY_MOOD: {'valence': 0.2, 'arousal':0.7, 'dominance':0.7}, 
        FEARFUL_MOOD: {'valence': 0.1, 'arousal':0.7, 'dominance':0.2}, 
        SAD_MOOD: {'valence': 0.1, 'arousal':0.2, 'dominance':0.2}, 
        CALM_MOOD: {'valence': 0.7, 'arousal':0.2, 'dominance':0.6}, 
        BORED_MOOD: {'valence': 0.3, 'arousal':0.1, 'dominance':0.3}, 
        EXCITED_MOOD: {'valence': 0.7, 'arousal':0.8, 'dominance':0.7}, 
        NEUTRAL_MOOD: {'valence': 0.5, 'arousal':0.5, 'dominance':0.5}, 
    }
    
    @staticmethod
    def distance(vad1: dict[str, float], vad2: dict[str, float]) -> float:
        return math.sqrt(
            (vad2['valence'] - vad1['valence']) ** 2 +
            (vad2['arousal'] - vad1['arousal']) ** 2 +
            (vad2['dominance'] - vad1['dominance']) ** 2
        )
    
    @classmethod
    def calculate_mood(cls, valence: float, arousal: float, dominance: float) -> dict[str, float]:
        input_vad = {'valence': valence, 'arousal': arousal, 'dominance': dominance}
        results = {
            mood: cls.distance(input_vad, output_vad) 
            for mood, output_vad in cls.VAD.items()
        }
        return results
    
    @staticmethod
    def top_mood(results: dict[str, float]) -> str:
        return min(results, key=results.get)
    
    @classmethod
    def get_top_mood(cls, valence: float, arousal: float, dominance: float) -> str:
        results = cls.calculate_mood(valence, arousal, dominance)
        return cls.top_mood(results)
    
    @staticmethod
    def top_n_moods(results: dict[str, float], n: int = 3) -> list[str]:
        return sorted(results, key=results.get)[:n]
    
    @classmethod
    def get_top_n_mood(cls, valence: float, arousal: float, dominance: float, n: int = 3) -> list[str]:
        results = cls.calculate_mood(valence, arousal, dominance)
        return cls.top_n_moods(results, n)
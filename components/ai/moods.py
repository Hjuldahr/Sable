import math
from typing import Iterable
import numpy as np

class Moods:
    # Mood IDs
    ANGRY = 0
    BORED = 1
    CALM = 2
    EXCITED = 3
    FEARFUL = 4
    JOYFUL = 5
    NEUTRAL = 6
    SAD = 7

    # Mood labels
    MOOD_LABELS = {
        ANGRY: 'angry',
        BORED: 'bored',
        CALM: 'calm',
        EXCITED: 'excited',
        FEARFUL: 'fearful',
        JOYFUL: 'joyful',
        NEUTRAL: 'neutral',
        SAD: 'sad'
    }

    # VAD vectors
    VAD = {
        JOYFUL: {'valence': 0.8, 'arousal': 0.7, 'dominance': 0.7},
        ANGRY: {'valence': 0.2, 'arousal': 0.7, 'dominance': 0.7},
        FEARFUL: {'valence': 0.1, 'arousal': 0.7, 'dominance': 0.2},
        SAD: {'valence': 0.1, 'arousal': 0.2, 'dominance': 0.2},
        CALM: {'valence': 0.7, 'arousal': 0.2, 'dominance': 0.6},
        BORED: {'valence': 0.3, 'arousal': 0.1, 'dominance': 0.3},
        EXCITED: {'valence': 0.7, 'arousal': 0.8, 'dominance': 0.7},
        NEUTRAL: {'valence': 0.5, 'arousal': 0.5, 'dominance': 0.5}
    }

    # Precompute VAD array for vectorized operations
    _VAD_ARRAY = np.array([
        [v['valence'], v['arousal'], v['dominance']] for v in VAD.values()
    ])

    @classmethod
    def ordinal(cls, n: int) -> str:
        return cls.MOOD_LABELS.get(n)

    @classmethod
    def ordinals(cls, ns: Iterable[int]) -> list[str]:
        return [cls.ordinal(n) for n in ns]

    @classmethod
    def calculate_mood(
        cls,
        valence: float,
        arousal: float,
        dominance: float,
        use_dominance: bool = True
    ) -> dict[int, float]:
        """Compute Euclidean distance from input VAD to all moods."""
        input_vec = np.array([valence, arousal, dominance])
        if not use_dominance:
            input_vec[2] = 0
            vad_array = cls._VAD_ARRAY.copy()
            vad_array[:, 2] = 0
        else:
            vad_array = cls._VAD_ARRAY

        distances = np.linalg.norm(vad_array - input_vec, axis=1)
        return {mood_id: dist for mood_id, dist in enumerate(distances)}

    @classmethod
    def get_top_mood(
        cls,
        valence: float,
        arousal: float,
        dominance: float,
        use_dominance: bool = True
    ) -> int:
        results = cls.calculate_mood(valence, arousal, dominance, use_dominance)
        return min(results, key=results.get)

    @classmethod
    def get_top_mood_label(
        cls,
        valence: float,
        arousal: float,
        dominance: float,
        use_dominance: bool = True
    ) -> str:
        return cls.ordinal(cls.get_top_mood(valence, arousal, dominance, use_dominance))

    @staticmethod
    def top_n_moods(results: dict[int, float], n: int = 3) -> list[int]:
        return sorted(results, key=results.get)[:n]

    @classmethod
    def get_top_n_moods(
        cls,
        valence: float,
        arousal: float,
        dominance: float,
        n: int = 3,
        use_dominance: bool = True
    ) -> list[int]:
        results = cls.calculate_mood(valence, arousal, dominance, use_dominance)
        return cls.top_n_moods(results, n)

    @staticmethod
    def mood_weights(
        results: dict[int, float],
        temperature: float = 1.0
    ) -> dict[int, float]:
        """Compute softmax-like weights inversely proportional to distance."""
        similarities = {m: 1 / (d + 1e-6) for m, d in results.items()}
        exp_vals = {m: math.exp(s / temperature) for m, s in similarities.items()}
        total = sum(exp_vals.values())
        return {m: v / total for m, v in exp_vals.items()}

    @classmethod
    def get_mood_weights(
        cls,
        valence: float,
        arousal: float,
        dominance: float,
        temperature: float = 1.0,
        use_dominance: bool = True
    ) -> dict[str, float]:
        """Return mood weights as a dict of label -> weight."""
        results = cls.calculate_mood(valence, arousal, dominance, use_dominance)
        weights = cls.mood_weights(results, temperature)
        return {cls.ordinal(k): v for k, v in weights.items()}

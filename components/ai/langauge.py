class Langauge:
    POSITIVE_WORDS = {"good", "great", "awesome", "happy", "fun", "love", "excited", "fantastic", "amazing"}
    NEGATIVE_WORDS = {"bad", "terrible", "sad", "angry", "hate", "annoyed", "frustrated", "boring", "awful"}
    HIGH_AROUSAL_WORDS = {"wow", "amazing", "excited", "urgent", "surprise"}
    LOW_AROUSAL_WORDS = {"calm", "relax", "quiet", "sleepy"}

    INTENSIFIERS = {"very": 1.5, "extremely": 2.0, "so": 1.2, "really": 1.3}
    NEGATIONS = {"not", "never", "no"}

    EMOJI_VALENCE = {
        "😀": 1.0, "😃": 0.9, "😄": 0.9, "😢": -0.8, "😭": -0.9, "😡": -0.9, "😍": 1.0, "😎": 0.8
    }
    EMOJI_AROUSAL = {
        "😀": 0.7, "😃": 0.8, "😄": 0.8, "😢": 0.4, "😭": 0.3, "😡": 0.9, "😍": 0.8, "😎": 0.6
    }
    
    INTEREST_VERBS = {
        "like", "love", "enjoy", "into", "obsessed", "addicted",
        "working on", "building", "learning", "studying", "playing"
    }

    INTENSIFIERS = {"really", "very", "super", "extremely", "so"}
    
    LIKE_VERBS = {
        "like", "love", "enjoy", "prefer", "adore", "favorite"
    }

    DISLIKE_VERBS = {
        "hate", "dislike", "can't stand", "annoying", "frustrating"
    }

    IMPORTANT_TERMS = {
        "deadline", "due", "important", "urgent", "asap",
        "meeting", "exam", "test", "project", "release"
    }

    TIME_TERMS = {
        "today", "tomorrow", "tonight", "next week", "soon"
    }
    
    FACT_PATTERNS = [
        # I am / I'm / I’m a X
        r"\b(i am|i'm|i'm)\s+(a|an)?\s*(?P<value>[a-zA-Z\s]+)",
        
        # I use / I work with / I work as
        r"\b(i use|i work with|i work as)\s+(?P<value>[a-zA-Z\s]+)",
        
        # My X is Y
        r"\bmy\s+(?P<key>[a-zA-Z\s]+)\s+is\s+(?P<value>[a-zA-Z0-9\s]+)",
        
        # I have X
        r"\b(i have)\s+(?P<value>[a-zA-Z0-9\s]+)"
    ]

    # Things we explicitly do NOT want to store as facts
    FACT_BLACKLIST = {
        "tired", "sad", "happy", "angry", "bored",
        "thinking", "trying", "learning", "considering",
        "busy", "stressed"
    }
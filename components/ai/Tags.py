class Tags:
    """enum-like holder for conversation tags"""
    SYS = 0
    USER = 1
    AI = 2
    
    SYS_TAG = "### instruction:"
    USER_TAG = "### user:"
    AI_TAG = "### assistant:"
    
    TAGS = {
        SYS: SYS_TAG,
        USER: USER_TAG,
        AI: AI_TAG
    }
    
    @classmethod
    def ordinal(cls, ord: int):
        return cls.TAGS.get(ord)
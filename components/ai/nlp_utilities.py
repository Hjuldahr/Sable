import re
import discord
import nltk

from .language import Language

class NLPUtilities:
    def __init__(self):
        nltk.download("punkt")
        nltk.download("averaged_perceptron_tagger")
        nltk.download("stopwords")
        self.nltk_stop_words = set(nltk.corpus.stopwords.words("english"))
        
    # Can be used to both profile users and evaulate AI persona alignment in the core   
        
    def extract_likes(self, message: discord.Message):
        pass
    
    def extract_dislikes(self, message: discord.Message):
        pass
    
    def extract_avoidances(self, message: discord.Message):
        pass
    
    def extract_passions(self, message: discord.Message):
        pass
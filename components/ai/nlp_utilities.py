import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Iterable
import discord
import nltk

class NLPUtilities:
    GENERIC_NOUNS = {
        "thing", "things", "stuff", "kind", "kinds", "type", "types"
    }

    CONTRAST_SPLIT_REGEX = re.compile(r"\b(but|however|though|except)\b", re.I)
    CHAR_BLACKLIST_REGEX = re.compile(r"[^\w\s\-]", re.I)
    NORM_WHITESPACE_REGEX = re.compile(r"\s+")

    FIND_LIKES_REGEX = (
        re.compile(r"\bi (really )?(like|love|enjoy|am into)\b(.+)", re.I),
        re.compile(r"\bfavorite\b(.+)", re.I),
    )
    FIND_DISLIKES_REGEX = (
        re.compile(r"\bi (really )?(hate|dislike|cant stand|don't like|do not like)\b(.+)", re.I),
    )
    FIND_AVOIDANCES_REGEX = (
        re.compile(r"\b(dont|do not) talk about\b(.+)", re.I),
        re.compile(r"\bplease avoid\b(.+)", re.I),
        re.compile(r"\bi don't want to discuss\b(.+)", re.I),
        re.compile(r"\bcan we not\b(.+)", re.I),
    )
    FIND_PASSIONS_REGEX = (
        re.compile(r"\bi am passionate about\b(.+)", re.I),
        re.compile(r"\bi want to learn\b(.+)", re.I),
        re.compile(r"\bi'm trying to get better at\b(.+)", re.I),
        re.compile(r"\bi spend a lot of time\b(.+)", re.I),
    )

    def __init__(self, n_threads = 4):
        if not nltk.data.find("tokenizers/punkt", None):
            nltk.download("punkt", quiet=True)
        if not nltk.data.find("tokenizers/averaged_perceptron_tagger", None):
            nltk.download("averaged_perceptron_tagger", quiet=True)
        if not nltk.data.find("corpora/stopwords", None):
            nltk.download("stopwords", quiet=True)
        self.nltk_stop_words = set(nltk.corpus.stopwords.words("english"))
        
        self.executor = ThreadPoolExecutor(max_workers=n_threads)

    # ---------- Internal helpers ----------

    def _clean_phrase(self, text: str) -> str:
        text = text.strip()
        text = self.CHAR_BLACKLIST_REGEX.sub("", text)
        text = self.NORM_WHITESPACE_REGEX.sub(" ", text)
        return text.lower()

    def _extract_noun_phrases(self, text: str) -> list[str]:
        tokens = nltk.word_tokenize(text)
        tagged = nltk.pos_tag(tokens)

        phrases: list[str] = []
        current: list[str] = []

        for word, tag in tagged:
            w = word.lower()
            if (
                tag.startswith("NN")
                and w not in self.nltk_stop_words
                and w not in self.GENERIC_NOUNS
            ):
                current.append(word)
            else:
                if current:
                    phrases.append(" ".join(current))
                    current = []

        if current:
            phrases.append(" ".join(current))

        return phrases

    def _extract_content(
        self,
        message: discord.Message,
        regx_set: Iterable[re.Pattern],
    ) -> list[str]:
        text = message.content
        contents: list[str] = []

        for regx in regx_set:
            match = regx.search(text)
            if not match:
                continue

            tail = match.group(match.lastindex)

            # Cut off contrast clauses: "but", "however", etc.
            tail = self.CONTRAST_SPLIT_REGEX.split(tail, maxsplit=1)[0]

            phrases = self._extract_noun_phrases(tail)
            contents.extend(phrases)

        cleaned = []
        seen = set()

        for phrase in contents:
            cleaned_phrase = self._clean_phrase(phrase)
            if cleaned_phrase and cleaned_phrase not in seen:
                seen.add(cleaned_phrase)
                cleaned.append(cleaned_phrase)

        return cleaned

    # ---------- Public extractors ----------

    def extract_likes(self, message: discord.Message) -> list[str]:
        return self._extract_content(message, self.FIND_LIKES_REGEX)

    def extract_dislikes(self, message: discord.Message) -> list[str]:
        return self._extract_content(message, self.FIND_DISLIKES_REGEX)

    def extract_avoidances(self, message: discord.Message) -> list[str]:
        return self._extract_content(message, self.FIND_AVOIDANCES_REGEX)

    def extract_passions(self, message: discord.Message) -> list[str]:
        return self._extract_content(message, self.FIND_PASSIONS_REGEX)
    
    async def extract_all(self, message: discord.Message) -> dict[str, list[str]]:
        return await asyncio.get_running_loop().run_in_executor(
            self.executor,
            self._extract_all_sync,
            message
        )

    def _extract_all_sync(self, message: discord.Message) -> dict[str, list[str]]:
        return {
            'likes': self._extract_content(message, self.FIND_LIKES_REGEX),
            'dislikes': self._extract_content(message, self.FIND_DISLIKES_REGEX),
            'avoidances': self._extract_content(message, self.FIND_AVOIDANCES_REGEX),
            'passions': self._extract_content(message, self.FIND_PASSIONS_REGEX),
        }
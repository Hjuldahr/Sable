import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Iterable, List, Dict
import nltk

class NaturalLanguageProcessor:
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

    def __init__(self, n_threads: int = 2):
        # Ensure nltk corpora are available
        for pkg in ("tokenizers/punkt", "taggers/averaged_perceptron_tagger", "corpora/stopwords"):
            try:
                nltk.data.find(pkg)
            except LookupError:
                nltk.download(pkg.split("/")[-1], quiet=True)

        self.nltk_stop_words = set(nltk.corpus.stopwords.words("english"))

        self.executor = ThreadPoolExecutor(
            max_workers=n_threads,
            thread_name_prefix="sable_nlp"
        )

    # ---------- Internal helpers ----------

    def close(self) -> None:
        self.executor.shutdown()

    def _clean_phrase(self, text: str) -> str:
        text = text.strip()
        text = self.CHAR_BLACKLIST_REGEX.sub("", text)
        text = self.NORM_WHITESPACE_REGEX.sub(" ", text)
        return text.lower()

    def _extract_noun_phrases(self, text: str) -> List[str]:
        tokens = nltk.word_tokenize(text)
        tagged = nltk.pos_tag(tokens)

        phrases: List[str] = []
        current: List[str] = []

        for word, tag in tagged:
            w = word.lower()
            if tag.startswith("NN") and w not in self.nltk_stop_words and w not in self.GENERIC_NOUNS:
                current.append(word)
            else:
                if current:
                    phrases.append(" ".join(current))
                    current = []

        if current:
            phrases.append(" ".join(current))

        return phrases

    def _extract_content(self, text: str, regex_set: Iterable[re.Pattern]) -> List[str]:
        contents: List[str] = []

        for regex in regex_set:
            match = regex.search(text)
            if not match:
                continue

            tail = match.group(match.lastindex)
            tail = self.CONTRAST_SPLIT_REGEX.split(tail, maxsplit=1)[0]

            phrases = self._extract_noun_phrases(tail)
            contents.extend(phrases)

        cleaned: List[str] = []
        seen: set[str] = set()

        for phrase in contents:
            cleaned_phrase = self._clean_phrase(phrase)
            if cleaned_phrase and cleaned_phrase not in seen:
                seen.add(cleaned_phrase)
                cleaned.append(cleaned_phrase)

        return cleaned

    # ---------- Public extractors ----------

    def extract_likes(self, text: str) -> List[str]:
        return self._extract_content(text, self.FIND_LIKES_REGEX)

    def extract_dislikes(self, text: str) -> List[str]:
        return self._extract_content(text, self.FIND_DISLIKES_REGEX)

    def extract_avoidances(self, text: str) -> List[str]:
        return self._extract_content(text, self.FIND_AVOIDANCES_REGEX)

    def extract_passions(self, text: str) -> List[str]:
        return self._extract_content(text, self.FIND_PASSIONS_REGEX)

    async def extract_all(self, text: str) -> Dict[str, List[str]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.executor,
            self._extract_all_sync,
            text
        )

    def _extract_all_sync(self, text: str) -> Dict[str, List[str]]:
        return {
            "likes": self.extract_likes(text),
            "dislikes": self.extract_dislikes(text),
            "avoidances": self.extract_avoidances(text),
            "passions": self.extract_passions(text),
        }
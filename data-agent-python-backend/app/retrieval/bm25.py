import math
import re
from collections import Counter
from dataclasses import dataclass


_ASCII_TERM = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*|\d+(?:\.\d+)?")
_CJK_BLOCK = re.compile(r"[\u3400-\u9fff]+")


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    tokens = _ASCII_TERM.findall(normalized)
    for block in _CJK_BLOCK.findall(normalized):
        tokens.extend(block)
        tokens.extend(block[index : index + 2] for index in range(len(block) - 1))
    return tokens


@dataclass(frozen=True)
class ScoredItem:
    index: int
    score: float


class Bm25Index:
    def __init__(self, texts: list[str], *, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = [Counter(tokenize(text)) for text in texts]
        self.lengths = [sum(document.values()) for document in self.documents]
        self.average_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        frequencies: Counter[str] = Counter()
        for document in self.documents:
            frequencies.update(document.keys())
        total = len(self.documents)
        self.idf = {
            term: math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in frequencies.items()
        }

    def search(self, query: str, top_k: int) -> list[ScoredItem]:
        query_terms = Counter(tokenize(query))
        scored: list[ScoredItem] = []
        for index, document in enumerate(self.documents):
            score = 0.0
            length_ratio = self.lengths[index] / self.average_length if self.average_length else 0.0
            for term, query_frequency in query_terms.items():
                frequency = document.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (1 - self.b + self.b * length_ratio)
                score += self.idf.get(term, 0.0) * frequency * (self.k1 + 1) / denominator * query_frequency
            if score > 0:
                scored.append(ScoredItem(index=index, score=score))
        scored.sort(key=lambda item: (-item.score, item.index))
        return scored[:top_k]

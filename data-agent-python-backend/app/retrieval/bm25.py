"""纯 Python 实现的 BM25 词法检索。

提供文本分词（兼顾英文与中文）与离线构建的 BM25 倒排打分索引，用于业务知识检索的
「词法召回」分支，与向量召回通过 RRF 融合（见 service.py）。

算法要点：
- 标准 Okapi BM25：score = IDF(term) * f * (k1+1) / (f + k1*(1 - b + b*L/Lavg))。
- k1 控制词频饱和度，b 控制文档长度归一化（抑制长文档的相对优势）。
- IDF 采用平滑形式 log(1 + (N - df + 0.5)/(df + 0.5))，避免负分。
- 中文按「字 + 二字滑动窗口」切分，兼顾单字与二元组匹配。
"""

import math
import re
from collections import Counter
from dataclasses import dataclass


# 英文/数字词元：连续字母数字或带小数点的数字
_ASCII_TERM = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*|\d+(?:\.\d+)?")
# 中日韩统一表意文字（CJK）连续区段
_CJK_BLOCK = re.compile(r"[\u3400-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """将文本切分为词元列表。

    英文与数字按正则切词并转小写；CJK 区段既保留单字，又补充相邻二字组（bigram），
    以缓解中文无空格导致的切分歧义。
    """
    normalized = text.lower()
    tokens = _ASCII_TERM.findall(normalized)
    for block in _CJK_BLOCK.findall(normalized):
        # 单字词元
        tokens.extend(block)
        # 相邻二字组，提升短语级匹配能力
        tokens.extend(block[index : index + 2] for index in range(len(block) - 1))
    return tokens


@dataclass(frozen=True)
class ScoredItem:
    """单个检索命中：文档在原列表中的索引与 BM25 得分。"""

    index: int
    score: float


class Bm25Index:
    """离线构建的 BM25 索引，支持 query 打分与 top_k 召回。"""

    def __init__(self, texts: list[str], *, k1: float = 1.5, b: float = 0.75):
        """构建索引并预计算 IDF。

        Args:
            texts: 待索引的文档文本列表。
            k1: 词频饱和参数，默认 1.5。
            b: 长度归一化参数，默认 0.75。
        """
        self.k1 = k1
        self.b = b
        # 每个文档的词频表
        self.documents = [Counter(tokenize(text)) for text in texts]
        # 各文档词元总数（用于长度归一化）
        self.lengths = [sum(document.values()) for document in self.documents]
        # 平均文档长度
        self.average_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        # 统计每个词元出现的文档数（df），用于 IDF
        frequencies: Counter[str] = Counter()
        for document in self.documents:
            frequencies.update(document.keys())
        total = len(self.documents)
        # 平滑 IDF：文档越稀有，权重越高
        self.idf = {
            term: math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in frequencies.items()
        }

    def search(self, query: str, top_k: int) -> list[ScoredItem]:
        """对 query 打分并返回 top_k 命中（按得分降序、索引升序稳定排序）。"""
        query_terms = Counter(tokenize(query))
        scored: list[ScoredItem] = []
        for index, document in enumerate(self.documents):
            score = 0.0
            # 文档长度相对平均长度的比值，用于 BM25 长度惩罚
            length_ratio = self.lengths[index] / self.average_length if self.average_length else 0.0
            for term, query_frequency in query_terms.items():
                frequency = document.get(term, 0)
                if not frequency:
                    continue
                # BM25 标准分母：词频 + k1*(1 - b + b*长度比)
                denominator = frequency + self.k1 * (1 - self.b + self.b * length_ratio)
                score += self.idf.get(term, 0.0) * frequency * (self.k1 + 1) / denominator * query_frequency
            if score > 0:
                scored.append(ScoredItem(index=index, score=score))
        # 得分高者优先；得分相同则索引小的在前，保证结果稳定
        scored.sort(key=lambda item: (-item.score, item.index))
        return scored[:top_k]

"""检索（retrieval）模块的公共出口。

对外导出知识检索核心服务 KnowledgeRetriever，负责在业务文档 / 证据 / 数据库 schema
之上执行混合检索（BM25 词法召回 + Chroma 向量召回，并用 RRF 融合），为下游的问答、
SQL 生成等流程提供相关上下文。
"""

from app.retrieval.service import KnowledgeRetriever

__all__ = ["KnowledgeRetriever"]

import asyncio
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

"""知识检索服务（KnowledgeRetriever）。

对业务文档、证据与数据库 schema 提供统一的混合检索能力：
- 词法召回：本地 BM25 索引（bm25.Bm25Index），无需外部依赖；
- 向量召回：可选 Chroma 集合（余弦相似度）；
- 融合：对两个分支用 RRF（Reciprocal Rank Fusion）合并排序。

数据来源有两种模式：
1. 离线模式（persisted_chunks）：直接读取本地 manifest 中的 chunk 记录；
2. 在线模式：从 recall_index_dir 下的 document-index.json / evidence-index.json 加载。

schema 检索额外做「关联表（join 邻居）扩展」，以保证跨表查询所需的相关表都被召回。
"""

from app.config import Settings
from app.retrieval.bm25 import Bm25Index
from app.retrieval.ingestion import KnowledgeManifest

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """在业务文档与证据之上执行 BM25 + Chroma 的混合检索。"""

    def __init__(self, settings: Settings):
        """初始化检索器，加载索引并（按配置）连接 Chroma。

        Args:
            settings: 全局配置（后端类型、各召回 top_k、RRF 参数等）。

        Raises:
            ValueError: retrieval_backend 既非 "chroma" 也非 "bm25" 时抛出。
        """
        self.settings = settings
        # 优先使用离线 manifest 中已经切分好的 chunk；否则回退到在线 JSON 索引
        self.persisted_chunks = settings.knowledge_manifest_path.exists()
        self.documents = self._load_persisted_chunks() if self.persisted_chunks else self._load("document-index.json")
        self.evidences = [] if self.persisted_chunks else self._load("evidence-index.json")
        # 为每个集合构建独立的 BM25 索引，以检索文本（标题+正文+标签）为输入
        self.document_index = Bm25Index([self._search_text(item) for item in self.documents])
        self.evidence_index = Bm25Index([self._search_text(item) for item in self.evidences])
        self.collection = None
        self._schema_fingerprint = ""
        self._schema_sync_lock = threading.Lock()
        if settings.retrieval_backend == "chroma":
            self.collection = self._initialize_chroma()
        elif settings.retrieval_backend != "bm25":
            raise ValueError(f"unsupported retrieval backend: {settings.retrieval_backend}")

    async def search(self, query: str) -> dict[str, list[dict[str, Any]]]:
        """检索业务文档与证据，返回 {"documents": [...], "evidences": [...]}。"""
        if self.collection is not None:
            # 有向量后端时走混合检索（词法+向量+RRF）
            return await asyncio.to_thread(self._hybrid_knowledge_search, query)
        # 仅 BM25 后端时，分别对各集合做纯词法排序
        return {
            "documents": self._rank(self.documents, self.document_index, query, self.settings.recall_document_top_k),
            "evidences": self._rank(self.evidences, self.evidence_index, query, self.settings.recall_evidence_top_k),
        }

    def _hybrid_knowledge_search(self, query: str) -> dict[str, list[dict[str, Any]]]:
        """同步执行文档与证据的混合检索（在 to_thread 中调用）。"""
        return {
            "documents": self._hybrid_rank(
                self.documents,
                self.document_index,
                # 离线模式 chunk 的 kind 为 knowledge_chunk，在线模式为 document
                "knowledge_chunk" if self.persisted_chunks else "document",
                query,
                self.settings.recall_document_top_k,
            ),
            "evidences": self._hybrid_rank(
                self.evidences, self.evidence_index, "evidence", query, self.settings.recall_evidence_top_k
            ),
        }

    async def search_schema(self, query: str, schema: dict[str, Any]) -> dict[str, Any]:
        """检索与查询相关的数据库表（含关联表扩展）。"""
        return await asyncio.to_thread(self._search_schema_sync, query, schema)

    def _search_schema_sync(self, query: str, schema: dict[str, Any]) -> dict[str, Any]:
        """先用混合检索挑出相关表，再保留直接关联的 join 邻居表。"""
        tables = [table for table in schema.get("tables", []) if isinstance(table, dict) and table.get("name")]
        items = [self._schema_item(table) for table in tables]
        if not items:
            return {"tables": [], "reasons": {}}
        # 对表集合临时构建 BM25 索引用于词法召回
        index = Bm25Index([self._search_text(item) for item in items])
        if self.collection is not None:
            # 用 schema 内容指纹判断是否需要把表同步进向量库（避免重复写入）
            fingerprint = hashlib.sha256(
                json.dumps(tables, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if fingerprint != self._schema_fingerprint:
                # 双重检查锁：仅首个进入的线程负责同步，避免并发重复写入
                with self._schema_sync_lock:
                    if fingerprint != self._schema_fingerprint:
                        self._sync_kind("schema_table", items)
                        self._schema_fingerprint = fingerprint
            ranked = self._hybrid_rank(
                items, index, "schema_table", query, min(self.settings.recall_schema_top_k, len(items))
            )
        else:
            ranked = self._rank(items, index, query, min(self.settings.recall_schema_top_k, len(items)))
        # 召回为空时兜底：取前 recall_schema_max_tables 张表，保证至少给出候选
        if not ranked:
            ranked = [self._result_item(item, 0.0) for item in items[: self.settings.recall_schema_max_tables]]
        # 去掉 schema: 前缀得到真实表名
        selected_names = [item["id"].removeprefix("schema:") for item in ranked]
        # 扩展直接 join 关联的邻居表，便于下游生成跨表 SQL
        selected_names = self._expand_join_neighbours(tables, selected_names)
        selected = [table for table in tables if table["name"] in selected_names]
        # 标记每个表的入选原因：命中 vs 关联扩展/兜底
        retrieved_names = {item["id"].removeprefix("schema:") for item in ranked if item["score"] > 0}
        reasons = {name: "混合检索命中" if name in retrieved_names else "关联表或召回兜底" for name in selected_names}
        return {"tables": selected, "reasons": reasons}

    def _initialize_chroma(self):
        """连接（必要时创建）Chroma 集合，并校验 embedding 模型一致性。"""
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        self.settings.chroma_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.settings.chroma_path))
        embedding_function = OpenAIEmbeddingFunction(
            api_key=self.settings.embedding_api_key,
            api_base=self.settings.embedding_api_base,
            model_name=self.settings.embedding_model,
        )
        try:
            existing = client.get_collection(self.settings.chroma_collection_name)
            indexed_model = (existing.metadata or {}).get("embedding:model")
            # 已索引模型与配置不一致说明需要重建索引，提示先跑 --rebuild
            if indexed_model != self.settings.embedding_model:
                raise RuntimeError(
                    "Chroma embedding model does not match configuration; run "
                    "`data-agent-index-knowledge --rebuild` before starting the backend "
                    f"(indexed={indexed_model}, configured={self.settings.embedding_model})"
                )
        except Exception as error:
            # 集合不存在属正常情况，真正的异常才向上抛出
            if error.__class__.__name__ not in {"NotFoundError", "InvalidCollectionException"}:
                raise
        collection = client.get_or_create_collection(
            name=self.settings.chroma_collection_name,
            embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine", "embedding:model": self.settings.embedding_model},
        )
        logger.info(
            "Chroma knowledge index connected: path=%s collection=%s embeddingModel=%s persistedChunks=%d",
            self.settings.chroma_path,
            self.settings.chroma_collection_name,
            self.settings.embedding_model,
            len(self.documents) if self.persisted_chunks else 0,
        )
        return collection

    def _sync_kind(self, kind: str, items: list[dict[str, Any]]) -> None:
        """把某类目（如 schema_table）的条目全量同步进向量库，并清理失效条目。"""
        ids = [self._storage_id(kind, item, index) for index, item in enumerate(items)]
        # 取出库中已有的同类目 id，计算需删除的失效 id
        stored_ids = set(self.collection.get(where={"kind": kind}, include=[])["ids"])
        stale_ids = list(stored_ids - set(ids))
        if stale_ids:
            self.collection.delete(ids=stale_ids)
        if items:
            self.collection.upsert(
                ids=ids,
                documents=[self._search_text(item) for item in items],
                metadatas=[
                    {"kind": kind, "payload": json.dumps(item, ensure_ascii=False)} for item in items
                ],
            )

    def _hybrid_rank(
        self,
        items: list[dict[str, Any]],
        index: Bm25Index,
        kind: str,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """融合词法与向量两个分支的结果（RRF）。

        Args:
            items: 候选条目（按原始顺序）。
            index: 该集合的 BM25 索引。
            kind: 向量库中用于 where 过滤的 kind。
            query: 查询文本。
            top_k: 最终返回条数。

        Returns:
            融合排序后的结果列表，score 为 RRF 累加分。

        RRF 公式：score += 1 / (k + rank)，k 为 recall_rrf_k，对两个分支分别累加。
        """
        if not items or top_k <= 0:
            return []
        # 召回候选数 = max(top_k, top_k * 倍率)，先扩大候选再做融合
        candidate_k = min(len(items), max(top_k, top_k * self.settings.recall_candidate_multiplier))
        lexical = self._rank(items, index, query, candidate_k)
        vector = self._vector_rank(kind, query, candidate_k)
        fused: dict[str, dict[str, Any]] = {}
        scores: dict[str, float] = {}
        # 两个分支各自按名次贡献 1/(k+rank) 的融合分，相同 id 累加
        for ranked in (lexical, vector):
            for rank, item in enumerate(ranked, start=1):
                item_id = item["id"]
                fused[item_id] = item
                scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (self.settings.recall_rrf_k + rank)
        # 按融合分降序、id 升序稳定排序后截断
        ordered = sorted(fused.values(), key=lambda item: (-scores[item["id"]], item["id"]))[:top_k]
        for item in ordered:
            item["score"] = round(scores[item["id"]], 6)
        return ordered

    def _vector_rank(self, kind: str, query: str, top_k: int) -> list[dict[str, Any]]:
        """执行向量召回并按相似度阈值过滤。"""
        result = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"kind": kind},
            include=["metadatas", "distances"],
        )
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        ranked = []
        for metadata, distance in zip(metadatas, distances, strict=False):
            # Chroma 余弦距离转相似度
            similarity = 1.0 - float(distance)
            if similarity < self.settings.recall_vector_min_score:
                continue
            item = self._item_from_vector_metadata(metadata)
            if item is None:
                logger.warning("Skipping Chroma result with invalid metadata: kind=%s", kind)
                continue
            ranked.append(self._result_item(item, similarity))
        return ranked

    @staticmethod
    def _item_from_vector_metadata(metadata: Any) -> dict[str, Any] | None:
        """从向量库元数据解码出检索条目。

        兼容两种格式：离线摄取写入的 record 字段，以及早期在线模式写入的 payload 字段。
        解析失败或结构不合法时返回 None（调用方会跳过该结果）。
        """
        if not isinstance(metadata, dict):
            return None
        raw = metadata.get("record") or metadata.get("payload")
        if not isinstance(raw, str):
            return None
        try:
            item = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(item, dict):
            return None
        # 离线格式把完整记录放在 record 字段，需规整为统一的 id/title/content/metadata 形态
        if "record" in metadata:
            item = {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "metadata": {
                    "source": item.get("sourcePath", metadata.get("source_path", "")),
                    "tags": item.get("headingPath", []),
                },
            }
        return item

    def _load(self, filename: str) -> list[dict[str, Any]]:
        """从 recall_index_dir 加载 JSON 数组格式的索引文件。"""
        path = Path(self.settings.recall_index_dir) / filename
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"recall index must be a JSON array: {path}")
        return [item for item in payload if isinstance(item, dict)]

    def _load_persisted_chunks(self) -> list[dict[str, Any]]:
        """从本地 manifest 读取离线切分好的 chunk 并规整为统一条目形态。"""
        records = KnowledgeManifest(self.settings.knowledge_manifest_path).records()
        return [
            {
                "id": record["id"],
                "title": record.get("title", ""),
                "content": record.get("content", ""),
                "metadata": {
                    "source": record.get("sourcePath", ""),
                    "tags": record.get("headingPath", []),
                },
            }
            for record in records
        ]

    @staticmethod
    def _search_text(item: dict[str, Any]) -> str:
        """构造用于检索的拼接文本：标题 + 正文 + 标签。"""
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
        return " ".join(
            [str(item.get("title") or ""), str(item.get("content") or ""), " ".join(map(str, tags))]
        )

    @staticmethod
    def _schema_item(table: dict[str, Any]) -> dict[str, Any]:
        """把数据库表结构转换为可检索条目（含字段说明与外键关系）。"""
        columns = table.get("columns", [])
        column_text = " ".join(
            f"{column.get('name', '')} {column.get('comment', '')} {column.get('dataType', '')}"
            for column in columns
        )
        relations = " ".join(
            f"{','.join(foreign_key.get('columns', []))} 关联 {foreign_key.get('referredTable', '')} "
            f"{','.join(foreign_key.get('referredColumns', []))}"
            for foreign_key in table.get("foreignKeys", [])
        )
        name = str(table["name"])
        return {
            "id": f"schema:{name}",
            "title": f"数据表 {name}",
            "content": f"表名 {name}。字段：{column_text}。外键关系：{relations}",
            "metadata": {"source": "live-schema", "tags": ["schema", name]},
        }

    def _expand_join_neighbours(self, tables: list[dict[str, Any]], selected: list[str]) -> list[str]:
        """基于外键关系保留直接 join 的邻居表，保证跨表查询所需表都被召回。

        仅当扩展后总数不超过 recall_schema_max_tables 时继续添加邻居，避免噪声膨胀。
        """
        neighbours: dict[str, set[str]] = {table["name"]: set() for table in tables}
        for table in tables:
            for foreign_key in table.get("foreignKeys", []):
                referred = foreign_key.get("referredTable")
                if referred in neighbours:
                    neighbours[table["name"]].add(referred)
                    neighbours[referred].add(table["name"])
        # 保持入选顺序、去重
        expanded = list(dict.fromkeys(selected))
        for name in list(expanded):
            for neighbour in sorted(neighbours.get(name, set())):
                if neighbour not in expanded and len(expanded) < self.settings.recall_schema_max_tables:
                    expanded.append(neighbour)
        return expanded

    @staticmethod
    def _storage_id(kind: str, item: dict[str, Any], index: int) -> str:
        """生成向量库存储 id：kind:原始id（缺省用序号），避免跨类目 id 冲突。"""
        return f"{kind}:{item.get('id') or index}"

    @staticmethod
    def _result_item(item: dict[str, Any], score: float) -> dict[str, Any]:
        """将检索条目与得分封装为统一的结果字典（含 source / tags）。"""
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        return {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "content": str(item.get("content") or ""),
            "score": round(score, 6),
            "source": str(metadata.get("source") or metadata.get("relativePath") or ""),
            "tags": metadata.get("tags") if isinstance(metadata.get("tags"), list) else [],
        }

    @staticmethod
    def _rank(
        items: list[dict[str, Any]], index: Bm25Index, query: str, top_k: int
    ) -> list[dict[str, Any]]:
        """纯 BM25 词法排序：按 BM25 命中重建结果列表。"""
        results = []
        for hit in index.search(query, top_k):
            item = items[hit.index]
            results.append(KnowledgeRetriever._result_item(item, hit.score))
        return results

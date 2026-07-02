import asyncio
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from app.config import Settings
from app.retrieval.bm25 import Bm25Index

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """Hybrid BM25 and Chroma retrieval over business documents and evidence."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.documents = self._load("document-index.json")
        self.evidences = self._load("evidence-index.json")
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
        if self.collection is not None:
            return await asyncio.to_thread(self._hybrid_knowledge_search, query)
        return {
            "documents": self._rank(self.documents, self.document_index, query, self.settings.recall_document_top_k),
            "evidences": self._rank(self.evidences, self.evidence_index, query, self.settings.recall_evidence_top_k),
        }

    def _hybrid_knowledge_search(self, query: str) -> dict[str, list[dict[str, Any]]]:
        return {
            "documents": self._hybrid_rank(
                self.documents, self.document_index, "document", query, self.settings.recall_document_top_k
            ),
            "evidences": self._hybrid_rank(
                self.evidences, self.evidence_index, "evidence", query, self.settings.recall_evidence_top_k
            ),
        }

    async def search_schema(self, query: str, schema: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._search_schema_sync, query, schema)

    def _search_schema_sync(self, query: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Shortlist tables with hybrid retrieval, then retain direct join neighbours."""
        tables = [table for table in schema.get("tables", []) if isinstance(table, dict) and table.get("name")]
        items = [self._schema_item(table) for table in tables]
        if not items:
            return {"tables": [], "reasons": {}}
        index = Bm25Index([self._search_text(item) for item in items])
        if self.collection is not None:
            fingerprint = hashlib.sha256(
                json.dumps(tables, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if fingerprint != self._schema_fingerprint:
                with self._schema_sync_lock:
                    if fingerprint != self._schema_fingerprint:
                        self._sync_kind("schema_table", items)
                        self._schema_fingerprint = fingerprint
            ranked = self._hybrid_rank(
                items, index, "schema_table", query, min(self.settings.recall_schema_top_k, len(items))
            )
        else:
            ranked = self._rank(items, index, query, min(self.settings.recall_schema_top_k, len(items)))
        if not ranked:
            ranked = [self._result_item(item, 0.0) for item in items[: self.settings.recall_schema_max_tables]]
        selected_names = [item["id"].removeprefix("schema:") for item in ranked]
        selected_names = self._expand_join_neighbours(tables, selected_names)
        selected = [table for table in tables if table["name"] in selected_names]
        retrieved_names = {item["id"].removeprefix("schema:") for item in ranked if item["score"] > 0}
        reasons = {name: "混合检索命中" if name in retrieved_names else "关联表或召回兜底" for name in selected_names}
        return {"tables": selected, "reasons": reasons}

    def _initialize_chroma(self):
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
            if indexed_model != self.settings.embedding_model:
                logger.info(
                    "Rebuilding Chroma collection after embedding model change: old=%s new=%s",
                    indexed_model,
                    self.settings.embedding_model,
                )
                client.delete_collection(self.settings.chroma_collection_name)
        except Exception as error:
            if error.__class__.__name__ not in {"NotFoundError", "InvalidCollectionException"}:
                raise
        collection = client.get_or_create_collection(
            name=self.settings.chroma_collection_name,
            embedding_function=embedding_function,
            metadata={"hnsw:space": "cosine", "embedding:model": self.settings.embedding_model},
        )
        records = [("document", item) for item in self.documents] + [("evidence", item) for item in self.evidences]
        for kind, items in (("document", self.documents), ("evidence", self.evidences)):
            self.collection = collection
            self._sync_kind(kind, items)
        logger.info(
            "Chroma knowledge index ready: path=%s collection=%s embeddingModel=%s records=%d",
            self.settings.chroma_path,
            self.settings.chroma_collection_name,
            self.settings.embedding_model,
            len(records),
        )
        return collection

    def _sync_kind(self, kind: str, items: list[dict[str, Any]]) -> None:
        ids = [self._storage_id(kind, item, index) for index, item in enumerate(items)]
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
        if not items or top_k <= 0:
            return []
        candidate_k = min(len(items), max(top_k, top_k * self.settings.recall_candidate_multiplier))
        lexical = self._rank(items, index, query, candidate_k)
        vector = self._vector_rank(kind, query, candidate_k)
        fused: dict[str, dict[str, Any]] = {}
        scores: dict[str, float] = {}
        for ranked in (lexical, vector):
            for rank, item in enumerate(ranked, start=1):
                item_id = item["id"]
                fused[item_id] = item
                scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (self.settings.recall_rrf_k + rank)
        ordered = sorted(fused.values(), key=lambda item: (-scores[item["id"]], item["id"]))[:top_k]
        for item in ordered:
            item["score"] = round(scores[item["id"]], 6)
        return ordered

    def _vector_rank(self, kind: str, query: str, top_k: int) -> list[dict[str, Any]]:
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
            similarity = 1.0 - float(distance)
            if similarity < self.settings.recall_vector_min_score:
                continue
            item = json.loads(metadata["payload"])
            ranked.append(self._result_item(item, similarity))
        return ranked

    def _load(self, filename: str) -> list[dict[str, Any]]:
        path = Path(self.settings.recall_index_dir) / filename
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"recall index must be a JSON array: {path}")
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _search_text(item: dict[str, Any]) -> str:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
        return " ".join(
            [str(item.get("title") or ""), str(item.get("content") or ""), " ".join(map(str, tags))]
        )

    @staticmethod
    def _schema_item(table: dict[str, Any]) -> dict[str, Any]:
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
        neighbours: dict[str, set[str]] = {table["name"]: set() for table in tables}
        for table in tables:
            for foreign_key in table.get("foreignKeys", []):
                referred = foreign_key.get("referredTable")
                if referred in neighbours:
                    neighbours[table["name"]].add(referred)
                    neighbours[referred].add(table["name"])
        expanded = list(dict.fromkeys(selected))
        for name in list(expanded):
            for neighbour in sorted(neighbours.get(name, set())):
                if neighbour not in expanded and len(expanded) < self.settings.recall_schema_max_tables:
                    expanded.append(neighbour)
        return expanded

    @staticmethod
    def _storage_id(kind: str, item: dict[str, Any], index: int) -> str:
        return f"{kind}:{item.get('id') or index}"

    @staticmethod
    def _result_item(item: dict[str, Any], score: float) -> dict[str, Any]:
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
        results = []
        for hit in index.search(query, top_k):
            item = items[hit.index]
            results.append(KnowledgeRetriever._result_item(item, hit.score))
        return results

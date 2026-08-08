from __future__ import annotations

"""知识库离线摄取（ingestion）管线。

将 TXT / Markdown 业务文档加载、按结构切分为 chunk、生成内容哈希，并写入本地 SQLite
manifest（记录文档哈希与 chunk）与可选的 Chroma 向量库。支持增量同步：仅重新处理
内容变动的文档，删除已移除文档对应的 chunk。

关键组件：
- KnowledgeSourceLoader：读取并规范化文档。
- KnowledgeChunker：结构优先的切分器（Markdown 标题分段 + 超大段落回退递归切分）。
- KnowledgeManifest：SQLite 持久化层，维护 source/chunk 状态以支持增量。
- KnowledgeIndexer：编排加载、切分、manifest 与向量库同步。
- ChromaChunkVectorStore：Chroma 向量库适配实现。
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence


# 仅支持纯文本与 Markdown 知识文档
SUPPORTED_SUFFIXES = {".md", ".txt"}


def _sha256(value: str) -> str:
    """计算 UTF-8 文本的 SHA-256 十六进制摘要，用作内容指纹。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceDocument:
    """加载后的单篇知识文档（不可变）。"""

    document_id: str
    source_path: str
    title: str
    content: str
    source_hash: str
    format: str


@dataclass(frozen=True)
class KnowledgeChunk:
    """切分后的知识块（不可变），是检索与索引的最小单元。"""

    chunk_id: str
    document_id: str
    source_path: str
    title: str
    heading_path: tuple[str, ...]
    content: str
    retrieval_text: str
    token_count: int
    chunk_index: int
    content_hash: str

    def to_record(self) -> dict[str, Any]:
        """序列化为可存入 manifest / 向量库元数据的字典。"""
        return {
            "id": self.chunk_id,
            "documentId": self.document_id,
            "sourcePath": self.source_path,
            "title": self.title,
            "headingPath": list(self.heading_path),
            "content": self.content,
            "retrievalText": self.retrieval_text,
            "tokenCount": self.token_count,
            "chunkIndex": self.chunk_index,
            "contentHash": self.content_hash,
        }


@dataclass(frozen=True)
class IndexingResult:
    """一次索引同步的统计结果。"""

    indexed_files: int = 0
    skipped_files: int = 0
    deleted_files: int = 0
    indexed_chunks: int = 0
    deleted_chunks: int = 0


class Tokenizer(Protocol):
    """分词器协议：仅需提供 encode 方法（与 HuggingFace tokenizers 兼容）。"""

    def encode(self, text: str, **kwargs: Any) -> Sequence[Any]: ...


class ChunkVectorStore(Protocol):
    """向量库适配协议：供 KnowledgeIndexer 注入，解耦具体向量实现。"""

    def upsert_chunks(self, chunks: Sequence[KnowledgeChunk]) -> None: ...

    def delete_chunks(self, chunk_ids: list[str]) -> None: ...


class KnowledgeSourceLoader:
    """读取并规范化知识源文档。"""

    def load(self, path: Path, source_root: Path) -> SourceDocument:
        """从磁盘加载一篇文档并生成内容指纹。

        Args:
            path: 文档绝对路径。
            source_root: 知识源根目录，用于计算相对路径作为稳定 document_id。

        Returns:
            规范化后的 SourceDocument（内容统一换行、去首尾空白、带 SHA-256 哈希）。

        Raises:
            ValueError: 文档后缀不在 SUPPORTED_SUFFIXES 时抛出。
        """
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported knowledge document: {path}")
        # 统一换行符并去首尾空白，保证内容哈希稳定
        content = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        relative_path = path.relative_to(source_root).as_posix()
        # Markdown 取首个一级标题作标题，否则用文件名
        title = self._markdown_title(content) if suffix == ".md" else path.stem
        return SourceDocument(
            document_id=relative_path.removesuffix(suffix),
            source_path=relative_path,
            title=title or path.stem,
            content=content,
            source_hash=_sha256(content),
            format=suffix.removeprefix("."),
        )

    @staticmethod
    def _markdown_title(content: str) -> str:
        """提取 Markdown 首个一级标题（# ）作为文档标题。"""
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""


class KnowledgeChunker:
    """结构优先的文档切分器；overlap 仅用于回退处理超大语义单元。"""

    # 递归切分的分隔符优先级：空行 > 换行 > 中英文句末标点 > 逗号/空格，最后逐字符
    _SEPARATORS = ["\n\n", "\n", "。", "！", "？", ". ", "! ", "? ", "；", "; ", "，", ", ", " ", ""]

    def __init__(self, tokenizer: Tokenizer, *, chunk_size: int = 512, chunk_overlap: int = 64):
        """初始化切分器并校验参数。

        Args:
            tokenizer: 用于精确统计 token 数的分词器。
            chunk_size: 单 chunk 的目标 token 上限。
            chunk_overlap: 超大段回退切分时的重叠 token 数。

        Raises:
            ValueError: chunk_size 非正或 overlap 越界时抛出。
        """
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_size must be positive and chunk_overlap must be smaller")
        self.tokenizer = tokenizer
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, document: SourceDocument) -> list[KnowledgeChunk]:
        """将一篇文档切分为带标题路径的 chunk 列表。"""
        # Markdown 按标题层级分段；纯文本视为单段
        sections = self._markdown_sections(document.content) if document.format == "md" else [((), document.content)]
        raw_chunks: list[tuple[tuple[str, ...], str]] = []
        for headings, section_text in sections:
            # 段落以空行划分
            paragraphs = [part.strip() for part in section_text.split("\n\n") if part.strip()]
            for paragraph in paragraphs:
                # 拼接标题前缀会占用部分预算，因此可用额度需扣除前缀长度
                prefix = " > ".join(headings)
                available = max(1, self.chunk_size - self._count(prefix + "\n" if prefix else ""))
                if self._count(paragraph) <= available:
                    # 段落本身在预算内，作为独立 chunk
                    raw_chunks.append((headings, paragraph))
                else:
                    # 超大段落回退到递归字符切分，并保留标题上下文
                    raw_chunks.extend((headings, part) for part in self._split_oversized(paragraph, available))

        chunks: list[KnowledgeChunk] = []
        for index, (headings, content) in enumerate(raw_chunks):
            # 检索文本 = 标题路径 + 正文，增强跨段落语义召回
            retrieval_text = self._contextualize(headings, content)
            content_hash = _sha256(retrieval_text)
            # chunk_id 同时绑定文档、序号与内容哈希，保证内容变动即生成新 id
            chunk_id = _sha256(f"{document.document_id}\n{index}\n{content_hash}")
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    source_path=document.source_path,
                    title=document.title,
                    heading_path=headings,
                    content=content,
                    retrieval_text=retrieval_text,
                    token_count=self._count(retrieval_text),
                    chunk_index=index,
                    content_hash=content_hash,
                )
            )
        return chunks

    def _split_oversized(self, text: str, chunk_size: int) -> list[str]:
        """将超长段落按分隔符递归切分为不超过 chunk_size 的若干片段。"""
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            # overlap 不能超过 chunk_size-1，避免死循环
            chunk_overlap=min(self.chunk_overlap, max(0, chunk_size - 1)),
            length_function=self._count,
            separators=self._SEPARATORS,
            keep_separator=False,
        )
        return [part.strip() for part in splitter.split_text(text) if part.strip()]

    def _markdown_sections(self, text: str) -> list[tuple[tuple[str, ...], str]]:
        """按 Markdown 标题（h1~h4）切分为带层级标题的段落。"""
        from langchain_text_splitters import MarkdownHeaderTextSplitter

        splitter = MarkdownHeaderTextSplitter(
            [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")],
            strip_headers=True,
        )
        sections = []
        for item in splitter.split_text(text):
            # 收集实际存在的标题层级，构成标题路径
            headings = tuple(str(item.metadata[key]) for key in ("h1", "h2", "h3", "h4") if item.metadata.get(key))
            if item.page_content.strip():
                sections.append((headings, item.page_content.strip()))
        return sections

    def _count(self, text: str) -> int:
        """用注入的分词器精确统计 token 数（不含特殊 token）。"""
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    @staticmethod
    def _contextualize(headings: tuple[str, ...], content: str) -> str:
        """将标题路径前缀拼接到正文前，作为检索文本以增强上下文。"""
        return f"{' > '.join(headings)}\n{content}" if headings else content


class KnowledgeManifest:
    """知识索引的本地 SQLite 持久化层。

    维护 knowledge_sources（文档哈希）与 knowledge_chunks（chunk 记录）两张表，
    用于判断哪些文档变动、需要重切分，以及删除文档时级联清理其 chunk。是增量索引
    的状态来源。"""

    def __init__(self, path: Path):
        """打开（必要时创建）manifest 数据库并建表。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        # 建表：sources 以 source_path 为主键；chunks 外键关联 sources，删除源时级联清理
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge_sources (
                source_path TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                chunk_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                record_json TEXT NOT NULL,
                FOREIGN KEY(source_path) REFERENCES knowledge_sources(source_path) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_source ON knowledge_chunks(source_path);
            """
        )

    def source_hash(self, source_path: str) -> str | None:
        """查询某文档的内容哈希；不存在则返回 None（用于判断是否需要重新索引）。"""
        row = self.connection.execute(
            "SELECT source_hash FROM knowledge_sources WHERE source_path = ?", (source_path,)
        ).fetchone()
        return str(row["source_hash"]) if row else None

    def source_paths(self) -> set[str]:
        """返回所有已记录文档的 source_path 集合。"""
        return {str(row["source_path"]) for row in self.connection.execute("SELECT source_path FROM knowledge_sources")}

    def chunk_ids(self, source_path: str) -> list[str]:
        """返回某文档按 chunk_index 排序的所有 chunk_id，用于计算失效 chunk。"""
        rows = self.connection.execute(
            "SELECT chunk_id FROM knowledge_chunks WHERE source_path = ? ORDER BY chunk_index", (source_path,)
        )
        return [str(row["chunk_id"]) for row in rows]

    def records(self) -> list[dict[str, Any]]:
        """返回所有 chunk 的反序列化记录（按 source_path、chunk_index 排序）。"""
        rows = self.connection.execute("SELECT record_json FROM knowledge_chunks ORDER BY source_path, chunk_index")
        return [json.loads(str(row["record_json"])) for row in rows]

    def replace(self, document: SourceDocument, chunks: Sequence[KnowledgeChunk]) -> None:
        """原子地替换某文档的 chunk 记录：先删旧 chunk，再 upsert 文档与 chunk。"""
        with self.connection:
            self.connection.execute("DELETE FROM knowledge_chunks WHERE source_path = ?", (document.source_path,))
            # 文档行 upsert：已存在则更新 document_id 与 source_hash
            self.connection.execute(
                """INSERT INTO knowledge_sources(source_path, document_id, source_hash) VALUES (?, ?, ?)
                   ON CONFLICT(source_path) DO UPDATE SET document_id=excluded.document_id, source_hash=excluded.source_hash""",
                (document.source_path, document.document_id, document.source_hash),
            )
            self.connection.executemany(
                "INSERT INTO knowledge_chunks(chunk_id, source_path, chunk_index, record_json) VALUES (?, ?, ?, ?)",
                [
                    (chunk.chunk_id, document.source_path, chunk.chunk_index, json.dumps(chunk.to_record(), ensure_ascii=False))
                    for chunk in chunks
                ],
            )

    def delete_source(self, source_path: str) -> None:
        """删除某文档及其全部 chunk（依赖外键级联删除 chunk）。"""
        with self.connection:
            self.connection.execute("DELETE FROM knowledge_chunks WHERE source_path = ?", (source_path,))
            self.connection.execute("DELETE FROM knowledge_sources WHERE source_path = ?", (source_path,))


class KnowledgeIndexer:
    """编排知识索引同步：加载 -> 切分 -> 同步 manifest 与向量库。"""

    def __init__(
        self,
        *,
        source_dir: Path,
        loader: KnowledgeSourceLoader,
        chunker: KnowledgeChunker,
        manifest: KnowledgeManifest,
        vector_store: ChunkVectorStore,
    ):
        """注入索引管线各组件。

        Args:
            source_dir: 知识源根目录。
            loader: 文档加载器。
            chunker: 切分器。
            manifest: 本地状态持久化层。
            vector_store: 向量库适配（Chroma 等）。
        """
        self.source_dir = source_dir
        self.loader = loader
        self.chunker = chunker
        self.manifest = manifest
        self.vector_store = vector_store

    def sync(self) -> IndexingResult:
        """执行一次增量索引同步。

        流程：
        1. 删除已不存在文档对应的 chunk 与源记录；
        2. 对现有文档，哈希未变则跳过，哈希变化则重新切分、upsert 新 chunk、删除失效 chunk；
        3. 汇总并返回索引统计。

        Returns:
            IndexingResult：本次新增/跳过/删除的文件与 chunk 数。
        """
        self.source_dir.mkdir(parents=True, exist_ok=True)
        # 递归收集所有受支持后缀的文件
        paths = sorted(path for path in self.source_dir.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES)
        current_sources = {path.relative_to(self.source_dir).as_posix() for path in paths}
        indexed_files = skipped_files = deleted_files = indexed_chunks = deleted_chunks = 0

        # 阶段一：清理磁盘上已被删除的文档（manifest 有但当前目录无）
        for source_path in sorted(self.manifest.source_paths() - current_sources):
            old_ids = self.manifest.chunk_ids(source_path)
            if old_ids:
                self.vector_store.delete_chunks(old_ids)
            self.manifest.delete_source(source_path)
            deleted_files += 1
            deleted_chunks += len(old_ids)

        # 阶段二：处理现有文档，按内容哈希做增量
        for path in paths:
            document = self.loader.load(path, self.source_dir)
            # 哈希一致说明内容未变，跳过切分与写入
            if self.manifest.source_hash(document.source_path) == document.source_hash:
                skipped_files += 1
                continue
            chunks = self.chunker.split(document)
            old_ids = self.manifest.chunk_ids(document.source_path)
            if chunks:
                self.vector_store.upsert_chunks(chunks)
            # 计算「旧有但不在新集合中的 chunk」，即失效 chunk 需删除
            new_ids = {chunk.chunk_id for chunk in chunks}
            stale_ids = [chunk_id for chunk_id in old_ids if chunk_id not in new_ids]
            if stale_ids:
                self.vector_store.delete_chunks(stale_ids)
                deleted_chunks += len(stale_ids)
            self.manifest.replace(document, chunks)
            indexed_files += 1
            indexed_chunks += len(chunks)

        return IndexingResult(indexed_files, skipped_files, deleted_files, indexed_chunks, deleted_chunks)


class ChromaChunkVectorStore:
    """Chroma 向量库的 ChunkVectorStore 适配实现。"""

    def __init__(self, collection: Any):
        """包装一个 Chroma collection。"""
        self.collection = collection

    def upsert_chunks(self, chunks: Sequence[KnowledgeChunk]) -> None:
        """将 chunk 批量写入 Chroma；以 retrieval_text 作为向量化文本，record 存于元数据。"""
        if not chunks:
            return
        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.retrieval_text for chunk in chunks],
            metadatas=[
                {
                    "kind": "knowledge_chunk",
                    "source_path": chunk.source_path,
                    "document_id": chunk.document_id,
                    "record": json.dumps(chunk.to_record(), ensure_ascii=False),
                }
                for chunk in chunks
            ],
        )

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        """从 Chroma 中删除指定 chunk_id。"""
        if chunk_ids:
            self.collection.delete(ids=chunk_ids)

"""测试知识库摄取（ingestion）与检索流程。

覆盖：Markdown / 纯文本的分块策略、增量索引（跳过未变更文件、替换变更块、删除已移除源）、
索引失败时的回滚保护，以及 BM25 检索器直接读取已持久化分块、无需重新处理源文件。
"""

from pathlib import Path

import pytest

from app.retrieval.ingestion import (
    KnowledgeChunker,
    KnowledgeIndexer,
    KnowledgeManifest,
    KnowledgeSourceLoader,
)
from app.config import Settings
from app.retrieval import KnowledgeRetriever


# 按空格切词的极简分词器，仅用于测试分块逻辑
class WordTokenizer:
    def encode(self, text: str, **_kwargs) -> list[str]:
        return text.split()


# 记录 upsert / delete 调用的假向量库，用于断言索引行为
class RecordingVectorStore:
    def __init__(self) -> None:
        self.upserts: list[list[dict]] = []
        self.deletes: list[list[str]] = []

    def upsert_chunks(self, chunks) -> None:
        self.upserts.append([chunk.to_record() for chunk in chunks])

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        self.deletes.append(chunk_ids)


# upsert 时抛错的向量库，用于验证索引失败时的回滚行为
class FailingVectorStore(RecordingVectorStore):
    def upsert_chunks(self, chunks) -> None:
        raise RuntimeError("embedding unavailable")


def test_markdown_chunking_preserves_heading_context_and_splits_oversized_section(tmp_path: Path) -> None:
    """验证 Markdown 分块会保留标题层级上下文，并对超长小节按 token 上限拆分。"""
    source = tmp_path / "sales.md"
    source.write_text(
        "# 销售指标\n\n## GMV\n\n"
        "one two three four five six seven eight nine ten eleven twelve\n\n"
        "## 退款额\n\nrefund amount rule",
        encoding="utf-8",
    )

    document = KnowledgeSourceLoader().load(source, tmp_path)
    chunks = KnowledgeChunker(WordTokenizer(), chunk_size=8, chunk_overlap=2).split(document)

    # 至少拆出 3 块；首块携带上层标题路径与可读的层级前缀
    assert len(chunks) >= 3
    assert chunks[0].heading_path == ("销售指标", "GMV")
    assert chunks[0].retrieval_text.startswith("销售指标 > GMV\n")
    # 末块属于“退款额”小节
    assert chunks[-1].heading_path == ("销售指标", "退款额")
    # 每块的 token 数不超过分块上限
    assert all(chunk.token_count <= 8 for chunk in chunks)


def test_text_chunking_prefers_paragraph_boundaries(tmp_path: Path) -> None:
    """验证纯文本分块优先按段落边界切分，而非机械地按 token 数切断。"""
    source = tmp_path / "rules.txt"
    source.write_text("one two three\n\nfour five six\n\nseven eight nine", encoding="utf-8")

    document = KnowledgeSourceLoader().load(source, tmp_path)
    chunks = KnowledgeChunker(WordTokenizer(), chunk_size=6, chunk_overlap=1).split(document)

    assert [chunk.content for chunk in chunks] == ["one two three", "four five six", "seven eight nine"]


def test_incremental_index_skips_unchanged_file_and_replaces_changed_chunks(tmp_path: Path) -> None:
    """验证增量索引：未变更文件被跳过，变更文件会删除旧块并 upsert 新块。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "rules.md"
    source.write_text("# Rules\n\nfirst version", encoding="utf-8")
    vector_store = RecordingVectorStore()
    manifest = KnowledgeManifest(tmp_path / "manifest.db")
    indexer = KnowledgeIndexer(
        source_dir=source_dir,
        loader=KnowledgeSourceLoader(),
        chunker=KnowledgeChunker(WordTokenizer(), chunk_size=20, chunk_overlap=2),
        manifest=manifest,
        vector_store=vector_store,
    )

    first = indexer.sync()
    second = indexer.sync()
    # 第一次同步后记录旧块 ID，随后修改源文件再次同步
    old_ids = manifest.chunk_ids("rules.md")
    source.write_text("# Rules\n\nsecond version changed", encoding="utf-8")
    third = indexer.sync()

    assert first.indexed_files == 1
    # 内容未变的第二次同步应被跳过
    assert second.skipped_files == 1
    assert third.indexed_files == 1
    # 变更后旧块被删除，仅产生两次 upsert（首次 + 变更后）
    assert vector_store.deletes == [old_ids]
    assert len(vector_store.upserts) == 2


def test_incremental_index_removes_chunks_for_deleted_source(tmp_path: Path) -> None:
    """验证源文件被删除后，增量索引会删除其对应分块并从清单中清除。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "obsolete.txt"
    source.write_text("obsolete rule", encoding="utf-8")
    vector_store = RecordingVectorStore()
    manifest = KnowledgeManifest(tmp_path / "manifest.db")
    indexer = KnowledgeIndexer(
        source_dir=source_dir,
        loader=KnowledgeSourceLoader(),
        chunker=KnowledgeChunker(WordTokenizer(), chunk_size=20, chunk_overlap=2),
        manifest=manifest,
        vector_store=vector_store,
    )
    indexer.sync()
    old_ids = manifest.chunk_ids("obsolete.txt")

    # 删除源文件后再次同步
    source.unlink()
    result = indexer.sync()

    assert result.deleted_files == 1
    assert vector_store.deletes == [old_ids]
    # 清单中该源的分块应已被清空
    assert manifest.chunk_ids("obsolete.txt") == []


def test_failed_reindex_keeps_previous_manifest_and_vectors(tmp_path: Path) -> None:
    """验证索引中途失败（向量库 upsert 抛错）时，旧的 manifest 与向量保持不变，不留下半截状态。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "rules.txt"
    source.write_text("first version", encoding="utf-8")
    manifest = KnowledgeManifest(tmp_path / "manifest.db")
    initial_store = RecordingVectorStore()
    chunker = KnowledgeChunker(WordTokenizer(), chunk_size=20, chunk_overlap=2)
    KnowledgeIndexer(
        source_dir=source_dir,
        loader=KnowledgeSourceLoader(),
        chunker=chunker,
        manifest=manifest,
        vector_store=initial_store,
    ).sync()
    original_ids = manifest.chunk_ids("rules.txt")
    source.write_text("second version", encoding="utf-8")
    failing_store = FailingVectorStore()

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        KnowledgeIndexer(
            source_dir=source_dir,
            loader=KnowledgeSourceLoader(),
            chunker=chunker,
            manifest=manifest,
            vector_store=failing_store,
        ).sync()

    # 失败回滚后，清单中的分块 ID 应与首次成功索引时一致
    assert manifest.chunk_ids("rules.txt") == original_ids
    # 失败的分库不应执行任何删除
    assert failing_store.deletes == []


@pytest.mark.asyncio
async def test_bm25_retriever_reads_persisted_chunks_without_reprocessing_sources(tmp_path: Path) -> None:
    """验证 BM25 检索器直接基于已持久化的分块（manifest）检索，无需重新处理源文件。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "sales.md").write_text("# 销售规则\n\n低库存商品指库存少于二十件的商品", encoding="utf-8")
    manifest_path = tmp_path / "manifest.db"
    manifest = KnowledgeManifest(manifest_path)
    KnowledgeIndexer(
        source_dir=source_dir,
        loader=KnowledgeSourceLoader(),
        chunker=KnowledgeChunker(WordTokenizer(), chunk_size=20, chunk_overlap=2),
        manifest=manifest,
        vector_store=RecordingVectorStore(),
    ).sync()

    retriever = KnowledgeRetriever(
        Settings(
            retrieval_backend="bm25",
            knowledge_manifest_path=manifest_path,
            recall_index_dir=tmp_path / "missing-legacy-index",
        )
    )
    result = await retriever.search("低库存商品")

    assert result["documents"][0]["source"] == "sales.md"
    assert "库存少于二十件" in result["documents"][0]["content"]

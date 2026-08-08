from __future__ import annotations

"""知识库离线索引 CLI。

将 TXT / Markdown 业务知识文档切分为 chunk，生成 embedding 后写入 Chroma 向量库，
并在本地 SQLite manifest 中维护文档哈希与 chunk 记录，支持增量索引与全量重建。

用法：
    python -m app.retrieval.index_cli            # 增量索引（仅处理变动文件）
    python -m app.retrieval.index_cli --rebuild  # 全量重建（重新 embedding 所有文档）
"""

import argparse
import logging

from app.config import get_settings
from app.retrieval.ingestion import (
    ChromaChunkVectorStore,
    KnowledgeChunker,
    KnowledgeIndexer,
    KnowledgeManifest,
    KnowledgeSourceLoader,
)


logger = logging.getLogger(__name__)


def _collection(settings, *, rebuild: bool):
    """获取（必要时重建）Chroma 集合，并返回是否需要强制全量重索引。

    Args:
        settings: 全局配置（路径、集合名、embedding 模型）。
        rebuild: 是否强制重建整个集合。

    Returns:
        (collection, force)，其中 force=True 表示应清空 manifest 哈希以触发全量重新 embedding。
    """
    import chromadb
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    force = rebuild
    try:
        existing = client.get_collection(settings.chroma_collection_name)
        indexed_model = (existing.metadata or {}).get("embedding:model")
        # 若显式重建，或已索引的 embedding 模型与配置不一致，则删除旧集合强制重建
        if rebuild or indexed_model != settings.embedding_model:
            client.delete_collection(settings.chroma_collection_name)
            force = True
    except Exception as error:
        # 集合不存在属正常情况，仅对真正的异常向上抛出
        if error.__class__.__name__ not in {"NotFoundError", "InvalidCollectionException"}:
            raise
    embedding_function = OpenAIEmbeddingFunction(
        api_key=settings.embedding_api_key,
        api_base=settings.embedding_api_base,
        model_name=settings.embedding_model,
    )
    collection = client.get_or_create_collection(
        name=settings.chroma_collection_name,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine", "embedding:model": settings.embedding_model},
    )
    return collection, force


def run(*, rebuild: bool = False) -> int:
    """执行一次索引同步，返回进程退出码（0 表示成功）。"""
    from tokenizers import Tokenizer

    settings = get_settings()
    collection, force = _collection(settings, rebuild=rebuild)
    tokenizer = Tokenizer.from_pretrained(settings.knowledge_tokenizer_model)
    manifest = KnowledgeManifest(settings.knowledge_manifest_path)
    # 强制重建时清空文档哈希，使所有文件被视为「未索引」而重新 embedding
    if force:
        manifest.connection.execute("UPDATE knowledge_sources SET source_hash = ''")
        manifest.connection.commit()
    # 组装加载→切分→持久化 manifest→写入向量库 的流水线并执行同步
    result = KnowledgeIndexer(
        source_dir=settings.knowledge_source_dir,
        loader=KnowledgeSourceLoader(),
        chunker=KnowledgeChunker(
            tokenizer,
            chunk_size=settings.knowledge_chunk_size,
            chunk_overlap=settings.knowledge_chunk_overlap,
        ),
        manifest=manifest,
        vector_store=ChromaChunkVectorStore(collection),
    ).sync()
    logger.info(
        "knowledge indexing complete: indexedFiles=%d skippedFiles=%d deletedFiles=%d "
        "indexedChunks=%d deletedChunks=%d",
        result.indexed_files,
        result.skipped_files,
        result.deleted_files,
        result.indexed_chunks,
        result.deleted_chunks,
    )
    return 0


def main() -> int:
    """CLI 入口：解析 --rebuild 参数并启动索引流程。"""
    parser = argparse.ArgumentParser(description="Index TXT and Markdown business knowledge into Chroma")
    parser.add_argument("--rebuild", action="store_true", help="re-embed every source document")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return run(rebuild=args.rebuild)


if __name__ == "__main__":
    raise SystemExit(main())

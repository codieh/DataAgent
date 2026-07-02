import json

import pytest

from app.config import Settings
from app.retrieval import KnowledgeRetriever
from app.retrieval.bm25 import tokenize


def _write_index(path, filename: str, items: list[dict]) -> None:
    (path / filename).write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
async def test_retrieves_chinese_business_rule_and_respects_top_k(tmp_path) -> None:
    _write_index(
        tmp_path,
        "document-index.json",
        [
            {"id": "inventory", "title": "库存规则", "content": "低库存商品指库存小于20的商品"},
            {"id": "sales", "title": "销量规则", "content": "销量按已完成订单的商品数量统计"},
        ],
    )
    _write_index(
        tmp_path,
        "evidence-index.json",
        [
            {"id": "gmv", "title": "GMV口径", "content": "成交总额只统计已完成订单"},
            {"id": "user", "title": "用户规则", "content": "用户通过用户编号关联订单"},
        ],
    )
    settings = Settings(
        recall_index_dir=tmp_path,
        retrieval_backend="bm25",
        recall_document_top_k=1,
        recall_evidence_top_k=1,
    )

    result = await KnowledgeRetriever(settings).search("分析低库存商品")

    assert [item["id"] for item in result["documents"]] == ["inventory"]
    assert len(result["evidences"]) <= 1
    assert result["documents"][0]["score"] > 0


@pytest.mark.asyncio
async def test_unrelated_query_does_not_fill_top_k(tmp_path) -> None:
    _write_index(tmp_path, "document-index.json", [{"id": "sales", "title": "销量", "content": "订单销量"}])
    _write_index(tmp_path, "evidence-index.json", [])
    settings = Settings(recall_index_dir=tmp_path, retrieval_backend="bm25")

    result = await KnowledgeRetriever(settings).search("天气怎么样")

    assert result == {"documents": [], "evidences": []}


def test_tokenizer_preserves_identifiers_and_chinese_overlap() -> None:
    tokens = tokenize("统计 order_items 的低库存商品")

    assert "order_items" in tokens
    assert "库存" in tokens


@pytest.mark.asyncio
async def test_schema_recall_keeps_relevant_table_and_join_neighbour(tmp_path) -> None:
    _write_index(tmp_path, "document-index.json", [])
    _write_index(tmp_path, "evidence-index.json", [])
    retriever = KnowledgeRetriever(Settings(recall_index_dir=tmp_path, retrieval_backend="bm25"))
    schema = {
        "tables": [
            {
                "name": "orders",
                "columns": [{"name": "id", "dataType": "BIGINT", "comment": "订单编号"}],
                "foreignKeys": [],
            },
            {
                "name": "order_items",
                "columns": [{"name": "quantity", "dataType": "INT", "comment": "商品销量"}],
                "foreignKeys": [
                    {"columns": ["order_id"], "referredTable": "orders", "referredColumns": ["id"]}
                ],
            },
            {
                "name": "users",
                "columns": [{"name": "name", "dataType": "VARCHAR", "comment": "用户名"}],
                "foreignKeys": [],
            },
        ]
    }

    result = await retriever.search_schema("统计商品销量", schema)

    names = [table["name"] for table in result["tables"]]
    assert "order_items" in names
    assert "orders" in names

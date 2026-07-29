"""测试知识检索（KnowledgeRetriever）与工具/提示词规范。

覆盖：BM25 中文业务规则检索与 top_k 限制、无关查询不填充结果、分词器对标识符与中文重叠词的处理、
工具规格隐藏运行时注入参数、Agent 系统提示词偏好合理默认值、向量离线分块元数据读取，
以及 schema 召回时保留相关表及其关联邻居表。
"""

import json

import pytest

from app.config import Settings
from app.retrieval import KnowledgeRetriever
from app.retrieval.bm25 import tokenize
from app.workflow.tools import AnalysisToolRegistry
from app.workflow.prompts import AGENT_SYSTEM


# 将索引条目写入指定 JSON 文件，供检索器读取
def _write_index(path, filename: str, items: list[dict]) -> None:
    (path / filename).write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
async def test_retrieves_chinese_business_rule_and_respects_top_k(tmp_path) -> None:
    """验证检索器能命中中文业务规则文档，并遵守 document/evidence 的 top_k 上限。"""
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
        knowledge_manifest_path=tmp_path / "missing-manifest.db",
        retrieval_backend="bm25",
        recall_document_top_k=1,
        recall_evidence_top_k=1,
    )

    result = await KnowledgeRetriever(settings).search("分析低库存商品")

    # 命中“库存”文档且为唯一一条（top_k=1）
    assert [item["id"] for item in result["documents"]] == ["inventory"]
    # 证据数量不超过 top_k
    assert len(result["evidences"]) <= 1
    assert result["documents"][0]["score"] > 0


@pytest.mark.asyncio
async def test_unrelated_query_does_not_fill_top_k(tmp_path) -> None:
    """验证与索引内容无关的查询返回空结果，不会强行填充 top_k。"""
    _write_index(tmp_path, "document-index.json", [{"id": "sales", "title": "销量", "content": "订单销量"}])
    _write_index(tmp_path, "evidence-index.json", [])
    settings = Settings(
        recall_index_dir=tmp_path,
        knowledge_manifest_path=tmp_path / "missing-manifest.db",
        retrieval_backend="bm25",
    )

    result = await KnowledgeRetriever(settings).search("天气怎么样")

    assert result == {"documents": [], "evidences": []}


def test_tokenizer_preserves_identifiers_and_chinese_overlap() -> None:
    """验证分词器保留英文标识符（如 order_items）与中文重叠词（如 库存）。"""
    tokens = tokenize("统计 order_items 的低库存商品")

    assert "order_items" in tokens
    assert "库存" in tokens


def test_tool_specifications_hide_runtime_injected_arguments() -> None:
    """验证工具规格只暴露给模型的必要参数，隐藏运行时注入参数与内部分析模式开关。"""
    registry = AnalysisToolRegistry(database=object(), retriever=object(), result_history=object())

    specifications = {item["name"]: item["parameters"] for item in registry.specifications()}

    assert set(specifications["execute_sql"]["properties"]) == {"sql", "purpose"}
    assert set(specifications["search_schema"]["properties"]) == {"query", "mode"}
    assert set(specifications["analyze_dataframe"]["properties"]) == {"objective", "dataset_ids"}
    assert set(specifications["search_history"]["properties"]) == {"query", "scope", "limit"}
    assert set(specifications["read_conversation_context"]["properties"]) == {
        "message_id",
        "before",
        "after",
    }
    assert set(specifications["inspect_query_result"]["properties"]) == {
        "dataset_id",
        "cursor",
        "limit",
    }
    for parameters in specifications.values():
        # 运行时注入参数不得出现在对外开放的工具参数中
        assert "state" not in parameters.get("properties", {})
        assert "tool_call_id" not in parameters.get("properties", {})


def test_tool_specifications_expose_runtime_execution_metadata() -> None:
    """工具运行属性应来自统一元数据表，供调度和可观测层使用。"""
    registry = AnalysisToolRegistry(database=object(), retriever=object(), result_history=object())
    specifications = {item["name"]: item["execution"] for item in registry.specifications()}

    assert specifications["search_schema"] == {
        "readOnly": True,
        "concurrencySafe": True,
        "requiresConfirmation": False,
        "resultPersistence": "summary",
    }
    assert specifications["execute_sql"]["concurrencySafe"] is False
    assert specifications["execute_sql"]["requiresConfirmation"] is True


def test_agent_uses_native_tool_schema_and_prefers_reasonable_defaults() -> None:
    """验证 Agent 系统提示词使用原生工具 schema、强调合理默认值，且将澄清作为最后手段。"""
    registry = AnalysisToolRegistry(database=object(), retriever=object(), result_history=object())
    descriptions = {item["name"]: item["description"] for item in registry.specifications()}

    assert "可用工具：" not in AGENT_SYSTEM
    assert "合理默认值" in AGENT_SYSTEM
    assert "最后手段" in descriptions["ask_clarification"]


def test_vector_rank_reads_offline_chunk_record_metadata(tmp_path) -> None:
    """验证向量检索排序能从离线分块记录的元数据里还原出 source 等字段。"""
    _write_index(tmp_path, "document-index.json", [])
    _write_index(tmp_path, "evidence-index.json", [])
    retriever = KnowledgeRetriever(
        Settings(
            recall_index_dir=tmp_path,
            knowledge_manifest_path=tmp_path / "missing-manifest.db",
            retrieval_backend="bm25",
            recall_vector_min_score=0.1,
        )
    )

    class Collection:
        def query(self, **_kwargs):
            return {
                "metadatas": [[
                    {
                        "kind": "knowledge_chunk",
                        "record": json.dumps(
                            {
                                "id": "chunk-1",
                                "title": "订单状态口径",
                                "content": "销售额仅统计已完成订单",
                                "sourcePath": "sales.md",
                                "headingPath": ["销售指标"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {"kind": "knowledge_chunk"},
                ]],
                "distances": [[0.1, 0.2]],
            }

    retriever.collection = Collection()

    # 从向量结果反查离线分块元数据，得到排序后的知识块
    ranked = retriever._vector_rank("knowledge_chunk", "销售额口径", 2)

    assert [item["id"] for item in ranked] == ["chunk-1"]
    # 分块的来源文件被正确还原
    assert ranked[0]["source"] == "sales.md"


@pytest.mark.asyncio
async def test_schema_recall_keeps_relevant_table_and_join_neighbour(tmp_path) -> None:
    """验证 schema 召回想关表时，也会带上与之有外键关联的邻居表（order_items 与 orders）。"""
    _write_index(tmp_path, "document-index.json", [])
    _write_index(tmp_path, "evidence-index.json", [])
    retriever = KnowledgeRetriever(
        Settings(
            recall_index_dir=tmp_path,
            knowledge_manifest_path=tmp_path / "missing-manifest.db",
            retrieval_backend="bm25",
        )
    )
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

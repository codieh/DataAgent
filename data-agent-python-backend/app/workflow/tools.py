"""分析 Agent 的领域工具集。

``AnalysisToolRegistry`` 把数据库查询、Schema 检索、知识召回、历史结果读取、
Python 分析等业务能力封装成 LangGraph 工具。工具执行、并发调度和统一日志
由 ``create_agent`` 及 ``DataAgentMiddleware`` 负责。
"""

import asyncio
import base64
import binascii
import json
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, BaseTool, tool
from langgraph.config import get_stream_writer
from langgraph.prebuilt import InjectedState
from langgraph.types import Command, interrupt

from app.infrastructure.datasource.sql import BusinessDatabase
from app.domain.errors import ResourceNotFoundError
from app.analysis.service import PythonAnalysisService
from app.analysis.datasets import AnalysisDatasetStore
from app.infrastructure.persistence.database import session_factory
from app.infrastructure.persistence.repository import Repository
from app.memory.core import CoreMemoryService
from app.retrieval import KnowledgeRetriever
from app.security import inspect_select_sql
from app.workflow.state import AnalysisState
from app.workflow.tool_results import (
    build_tool_result,
    json_default,
)
from app.workflow.tool_metadata import tool_metadata


class AnalysisToolRegistry:
    """Creates LangGraph tools while keeping business dependencies explicit."""

    def __init__(
        self,
        database: BusinessDatabase,
        retriever: KnowledgeRetriever,
        python_analysis: PythonAnalysisService | None = None,
        dataset_store: AnalysisDatasetStore | None = None,
        result_history: Any | None = None,
        core_memory: CoreMemoryService | None = None,
    ):
        self.database = database
        self.retriever = retriever
        self.python_analysis = python_analysis
        self.dataset_store = dataset_store
        self.result_history = result_history
        self.core_memory = core_memory
        self.tools = self._build()

    def _build(self) -> list[BaseTool]:
        database = self.database
        retriever = self.retriever
        python_analysis = self.python_analysis
        dataset_store = self.dataset_store
        result_history = self.result_history
        core_memory = self.core_memory

        @tool("update_analysis_plan", description="记录或更新复杂分析任务的目标和执行步骤。简单查询无需调用。")
        async def update_analysis_plan(
            goal: str,
            steps: list[dict[str, Any]],
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            normalized_steps = [
                {
                    "id": str(step.get("id") or f"step_{index:02d}"),
                    "title": str(step.get("title") or "分析步骤"),
                    "objective": str(step.get("objective") or step.get("title") or ""),
                }
                for index, step in enumerate(steps[:10], start=1)
                if isinstance(step, dict)
            ]
            plan = {"goal": goal, "steps": normalized_steps}
            feedback = state.get("human_feedback", {})
            if feedback.get("comment"):
                plan["review_feedback"] = feedback["comment"]
            observation = {
                "tool": "update_analysis_plan",
                "ok": True,
                "summary": f"已记录 {len(normalized_steps)} 个分析步骤",
            }
            return _command(
                tool_call_id,
                observation,
                plan=plan,
                observations=[observation],
            )

        @tool(
            "ask_clarification",
            description=(
                "澄清是最后手段：仅当已检索 Schema 和业务知识后仍缺少不可推断的决定性条件，"
                "且任何合理默认值都会改变用户核心意图时使用。"
            ),
        )
        async def ask_clarification(
            question: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            observation = {"tool": "ask_clarification", "ok": True, "summary": question}
            return _command(
                tool_call_id,
                observation,
                final_answer=question,
                result_mode="need_clarification",
                observations=[observation],
            )

        @tool(
            "search_schema",
            description=(
                "检索数据表。mode=relevance 根据问题召回相关表及字段；"
                "mode=catalog 仅列出真实表名和注释，用于不知道数据库有哪些表时浏览目录。"
            ),
        )
        async def search_schema(
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            query: str = "",
            mode: str = "relevance",
        ) -> Command:
            _progress("正在检索相关数据表")
            if mode not in {"relevance", "catalog"}:
                raise ValueError("search_schema.mode 只能是 relevance 或 catalog")
            full_schema = state.get("full_schema") or await database.schema_snapshot()
            if mode == "catalog":
                catalog = [
                    {
                        "name": table.get("name"),
                        "comment": table.get("comment", ""),
                    }
                    for table in full_schema.get("tables", [])
                ]
                observation = {
                    "tool": "search_schema",
                    "ok": bool(catalog),
                    "query": query,
                    "mode": mode,
                    "summary": f"数据库共有 {len(catalog)} 张表",
                    "tableNames": [item["name"] for item in catalog],
                }
                return _command(
                    tool_call_id,
                    observation,
                    tool_content=build_tool_result(
                        observation,
                        preview={"tables": catalog},
                        result_ref="schema:catalog",
                        stats={"tableCount": len(catalog)},
                        available_actions=["inspect_tables", "search_schema"],
                    ),
                    # catalog 只缓存完整快照，不把目录误当成已完成的相关表召回。
                    full_schema=full_schema,
                    observations=[observation],
                )

            previous = _successful_observation(state, "search_schema", f"{mode}:{query}")
            if previous is not None and state.get("schema", {}).get("tables"):
                selected = list(state.get("selected_tables") or [])
                observation = {
                    "tool": "search_schema",
                    "ok": True,
                    "query": f"{mode}:{query}",
                    "reused": True,
                    "summary": "相同 Schema 检索已成功完成，复用现有候选表，请继续下一步",
                    "tableNames": selected,
                }
                return _command(
                    tool_call_id,
                    observation,
                    tool_content=build_tool_result(
                        observation,
                        result_ref="schema:current",
                        stats={"tableCount": len(selected), "tableNames": selected, "reused": True},
                        available_actions=["inspect_tables"],
                    ),
                    observations=[observation],
                )
            recalled = await retriever.search_schema(query, full_schema)
            selected = [table["name"] for table in recalled["tables"]]
            observation = {
                "tool": "search_schema",
                "ok": bool(selected),
                "query": f"{mode}:{query}",
                "mode": mode,
                "summary": f"召回 {selected} 作为候选表",
                "tableNames": selected,
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"tables": recalled["tables"]},
                    result_ref="schema:current",
                    stats={"tableCount": len(recalled["tables"]), "tableNames": selected},
                    available_actions=["inspect_tables"],
                ),
                full_schema=full_schema,
                schema={"tables": recalled["tables"]},
                selected_tables=selected,
                schema_reasons=recalled["reasons"],
                schema_search_count=state.get("schema_search_count", 0) + 1,
                observations=[observation],
            )

        @tool("inspect_tables", description="读取指定真实数据表的完整字段和关联关系。")
        async def inspect_tables(
            tables: list[str],
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            _progress("正在读取指定表结构")
            names = {str(name) for name in tables if str(name).strip()}
            full_schema = state.get("full_schema") or await database.schema_snapshot()
            inspected = [table for table in full_schema.get("tables", []) if table.get("name") in names]
            merged = {table.get("name"): table for table in state.get("schema", {}).get("tables", [])}
            merged.update({table.get("name"): table for table in inspected})
            observation = {
                "tool": "inspect_tables",
                "ok": bool(inspected),
                "summary": f"读取 {len(inspected)} 张表的完整结构" if inspected else "请求的表不存在",
                "tableNames": [table.get("name") for table in inspected],
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"tables": inspected},
                    result_ref="schema:current",
                    stats={
                        "tableCount": len(inspected),
                        "tableNames": [table.get("name") for table in inspected],
                    },
                    available_actions=["inspect_tables"],
                ),
                full_schema=full_schema,
                schema={"tables": list(merged.values())},
                selected_tables=list(merged),
                observations=[observation],
            )

        @tool("retrieve_knowledge", description="检索与指标口径、业务术语和默认规则相关的业务知识。")
        async def retrieve_knowledge(
            query: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            _progress("正在检索业务知识")
            previous = _successful_observation(state, "retrieve_knowledge", query)
            if previous is not None and state.get("knowledge"):
                knowledge = state["knowledge"]
                count = len(knowledge.get("documents", [])) + len(knowledge.get("evidences", []))
                observation = {
                    "tool": "retrieve_knowledge",
                    "ok": True,
                    "query": query,
                    "reused": True,
                    "summary": "相同业务知识检索已成功完成，复用现有结果，请继续下一步",
                }
                return _command(
                    tool_call_id,
                    observation,
                    tool_content=build_tool_result(
                        observation,
                        result_ref="knowledge:current",
                        stats={
                            "documentCount": len(knowledge.get("documents", [])),
                            "evidenceCount": len(knowledge.get("evidences", [])),
                            "reused": True,
                        },
                        available_actions=["retrieve_knowledge"],
                    ),
                    observations=[observation],
                )
            knowledge = await retriever.search(query)
            count = len(knowledge["documents"]) + len(knowledge["evidences"])
            observation = {
                "tool": "retrieve_knowledge",
                "ok": count > 0,
                "query": query,
                "summary": f"召回 {count} 条业务知识",
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview=knowledge,
                    result_ref="knowledge:current",
                    stats={
                        "documentCount": len(knowledge["documents"]),
                        "evidenceCount": len(knowledge["evidences"]),
                    },
                    available_actions=["retrieve_knowledge"],
                ),
                knowledge=knowledge,
                observations=[observation],
            )

        @tool(
            "execute_sql",
            description=(
                "安全校验并执行一条只读 MySQL SELECT。purpose=explore 表示为后续分析探查数据，"
                "purpose=deliver 表示产生面向用户的交付结果；两者执行相同的安全校验。"
            ),
        )
        async def execute_sql(
            sql: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            purpose: str = "deliver",
        ) -> Command:
            """在一次原生工具调用内完成校验、审核和执行，只返回最终结果。"""
            if purpose not in {"explore", "deliver"}:
                raise ValueError("execute_sql.purpose 只能是 explore 或 deliver")
            _progress("正在检查并执行 SQL")
            policy = inspect_select_sql(
                sql,
                row_limit=database.settings.sql_row_limit,
                schema=state.get("schema", {}),
                sensitive_fields=retriever.settings.sql_sensitive_field_list,
            )
            if not policy.passed:
                _sql_event(
                    "sql.blocked",
                    {
                        "candidateSql": sql,
                        "reason": policy.reason,
                        "resultMode": policy.result_mode,
                        "retryable": policy.retryable,
                    },
                )
                repair_count = state.get("retry_count", 0) + int(policy.retryable)
                repair_exhausted = (
                    policy.retryable
                    and repair_count > retriever.settings.agent_max_sql_repairs
                )
                observation = {
                    "tool": "execute_sql",
                    "ok": False,
                    "summary": "SQL 安全校验未通过",
                    "error": policy.reason,
                    "resultMode": policy.result_mode,
                    "retryable": policy.retryable and not repair_exhausted,
                }
                updates: dict[str, Any] = {
                    "sql": sql,
                    "sql_error": policy.reason,
                    "safety": {
                        "passed": False,
                        "reason": policy.reason,
                        "checks": policy.checks,
                        "resultMode": policy.result_mode,
                    },
                    "retry_count": repair_count,
                    "observations": [observation],
                }
                if not policy.retryable or repair_exhausted:
                    updates["result_mode"] = (
                        policy.result_mode
                        if not repair_exhausted
                        else "sql_repair_exhausted"
                    )
                    updates["error"] = (
                        policy.reason
                        if not repair_exhausted
                        else f"SQL 连续校验失败，已停止自动修复：{policy.reason}"
                    )
                return _command(tool_call_id, observation, **updates)

            safe_sql = policy.sql
            safety = {
                "passed": True,
                "readOnly": True,
                "limitApplied": "LIMIT" in safe_sql.upper(),
                "sensitiveFields": [],
                "checks": policy.checks,
            }
            _sql_event(
                "sql.validated",
                {
                    "sql": safe_sql,
                    "safety": safety,
                },
            )

            # 同一 Run 已成功执行过完全相同的规范化 SQL 时复用结果，避免模型重试
            # 造成重复数据库访问和重复结果集。
            existing = next(
                (
                    item
                    for item in reversed(state.get("query_results", []))
                    if str(item.get("sql") or "").strip() == safe_sql.strip()
                ),
                None,
            )
            if existing is not None:
                dataset_id = str(existing.get("datasetId") or "")
                _sql_event(
                    "sql.reused",
                    {
                        "sql": safe_sql,
                        "resultSetId": dataset_id,
                        "rowCount": int(existing.get("rowCount") or 0),
                    },
                )
                observation = {
                    "tool": "execute_sql",
                    "ok": True,
                    "summary": "相同 SQL 已执行成功，直接复用已有结果",
                    "rowCount": int(existing.get("rowCount") or 0),
                    "datasetId": dataset_id,
                    "purpose": purpose,
                    "reused": True,
                }
                return _command(
                    tool_call_id,
                    observation,
                    tool_content=build_tool_result(
                        observation,
                        result_ref=f"result:{dataset_id}",
                        stats={
                            "rowCount": observation["rowCount"],
                            "datasetId": dataset_id,
                            "reused": True,
                        },
                        available_actions=["inspect_query_result"],
                    ),
                    sql=safe_sql,
                    sql_error=None,
                    safety=safety,
                    observations=[observation],
                )

            human_feedback = {"approved": True, "comment": ""}
            if (
                state.get("human_review_enabled")
                and tool_metadata("execute_sql").requires_confirmation
            ):
                _progress("SQL 已通过安全检查，等待人工审核")
                _sql_event(
                    "sql.review_required",
                    {
                        "sql": safe_sql,
                        "tables": state.get("selected_tables", []),
                        "safety": safety,
                    },
                )
                human_feedback = dict(
                    interrupt(
                        {
                            "sql": safe_sql,
                            "plan": state.get("plan"),
                            "safety": safety,
                            "tables": state.get("selected_tables", []),
                        }
                    )
                    or {}
                )
                if not human_feedback.get("approved", False):
                    comment = human_feedback.get("comment") or "人工审核未通过"
                    _sql_event(
                        "sql.rejected",
                        {"sql": safe_sql, "reason": comment},
                    )
                    observation = {
                        "tool": "execute_sql",
                        "ok": False,
                        "summary": "SQL 未执行：人工审核未通过",
                        "error": comment,
                        "retryable": True,
                    }
                    plan = dict(state.get("plan") or {})
                    plan["review_feedback"] = comment
                    return _command(
                        tool_call_id,
                        observation,
                        sql=safe_sql,
                        sql_error=comment,
                        safety=safety,
                        human_feedback=human_feedback,
                        plan=plan,
                        observations=[observation],
                    )

            if dataset_store is None:
                raise RuntimeError("分析数据集存储未配置")
            try:
                _sql_event("sql.executing", {"sql": safe_sql})
                columns, rows = await database.execute_select(
                    safe_sql,
                    row_limit=database.settings.sql_row_limit,
                )
                dataset = await dataset_store.create(
                    run_id=state["run_id"],
                    columns=columns,
                    rows=rows,
                )
            except Exception as error:
                _sql_event(
                    "sql.failed",
                    {"sql": safe_sql, "error": str(error)},
                )
                observation = {
                    "tool": "execute_sql",
                    "ok": False,
                    "summary": "SQL 执行失败",
                    "error": str(error),
                    "retryable": True,
                }
                return _command(
                    tool_call_id,
                    observation,
                    sql=safe_sql,
                    columns=[],
                    rows=[],
                    sql_error=str(error),
                    safety=safety,
                    human_feedback=human_feedback,
                    retry_count=state.get("retry_count", 0) + 1,
                    sql_execution_count=state.get("sql_execution_count", 0) + 1,
                    observations=[observation],
                )

            preview = dataset["previewRows"]
            query_result = {
                "sql": safe_sql,
                "columns": columns,
                "rowCount": len(rows),
                "datasetId": dataset["id"],
                "purpose": purpose,
                "dataset": {
                    "id": dataset["id"],
                    "rowCount": dataset["rowCount"],
                    "filePath": dataset["filePath"],
                },
            }
            _sql_event(
                "sql.executed",
                {
                    "sql": safe_sql,
                    "resultSetId": dataset["id"],
                    "rowCount": len(rows),
                },
            )
            observation = {
                "tool": "execute_sql",
                "ok": True,
                "summary": f"查询成功，返回 {len(rows)} 行",
                "rowCount": len(rows),
                "datasetId": dataset["id"],
                "purpose": purpose,
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"columns": columns, "rows": preview},
                    result_ref=f"result:{dataset['id']}",
                    stats={
                        "rowCount": len(rows),
                        "datasetId": dataset["id"],
                        "purpose": purpose,
                    },
                    available_actions=["inspect_query_result"],
                ),
                sql=safe_sql,
                columns=columns,
                rows=preview,
                sql_error=None,
                result_mode="success",
                safety=safety,
                human_feedback=human_feedback,
                sql_execution_count=state.get("sql_execution_count", 0) + 1,
                query_results=[*state.get("query_results", []), query_result],
                analysis_datasets=[*state.get("analysis_datasets", []), dataset],
                observations=[observation],
            )

        @tool(
            "search_history",
            description=(
                "统一搜索历史消息和历史查询结果。scope=current 仅查当前会话；"
                "scope=all 还会搜索同一数据源的其他会话。返回条目会明确类型和后续读取工具。"
            ),
        )
        async def search_history(
            query: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            scope: str = "all",
            limit: int = 5,
        ) -> Command:
            if scope not in {"current", "all"}:
                raise ValueError("search_history.scope 只能是 current 或 all")
            effective_limit = min(max(limit, 1), 10)

            async def search_messages() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
                async with session_factory() as session:
                    repository = Repository(session)
                    anchor = await repository.get_conversation(state["conversation_id"])
                    if anchor is None:
                        raise ResourceNotFoundError(
                            "conversation",
                            state["conversation_id"],
                        )
                    current = await repository.search_current_conversation_history(
                        state["conversation_id"],
                        query,
                        effective_limit * 2,
                        exclude_run_id=state.get("run_id"),
                    )
                    if scope == "current":
                        return current, []
                    cross = await repository.search_conversation_history(
                        query,
                        effective_limit * 3,
                        datasource_id=anchor.datasource_id,
                    )
                    cross = [
                        item
                        for item in cross
                        if item.get("conversationId") != state["conversation_id"]
                    ]
                    return current, cross

            result_task = (
                result_history.search(
                    state["conversation_id"],
                    query,
                    "all",
                    effective_limit * 2,
                )
                if result_history is not None
                else asyncio.sleep(0, result=[])
            )
            (current_messages, cross_messages), result_matches = await asyncio.gather(
                search_messages(),
                result_task,
            )
            matches = _merge_history_matches(
                current_messages=current_messages,
                cross_messages=cross_messages,
                result_matches=result_matches,
                limit=effective_limit,
            )
            observation = {
                "tool": "search_history",
                "ok": bool(matches),
                "summary": f"找到 {len(matches)} 条相关历史线索",
                "resultCount": len(matches),
                "scope": scope,
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"matches": matches},
                    result_ref="history:search",
                    stats={
                        "matchCount": len(matches),
                        "messageMatchCount": len(current_messages) + len(cross_messages),
                        "resultMatchCount": len(result_matches),
                    },
                    available_actions=[
                        "read_conversation_context",
                        "inspect_query_result",
                    ],
                ),
                observations=[observation],
            )

        @tool(
            "read_conversation_context",
            description=(
                "根据 search_history 返回的 messageId，读取该消息及前后原始对话。"
                "服务端会验证消息与当前会话使用相同数据源。"
            ),
        )
        async def read_conversation_context(
            message_id: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            before: int = 2,
            after: int = 2,
        ) -> Command:
            async with session_factory() as session:
                result = await Repository(session).read_accessible_message_context(
                    state["conversation_id"],
                    message_id,
                    min(max(before, 0), 10),
                    min(max(after, 0), 10),
                )
            observation = {
                "tool": "read_conversation_context",
                "ok": bool(result["messages"]),
                "summary": f"读取命中消息附近的 {len(result['messages'])} 条原始消息",
                "messageId": message_id,
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview=result,
                    result_ref=f"message:{message_id}",
                    stats={"messageCount": len(result["messages"])},
                    available_actions=["read_conversation_context"],
                ),
                observations=[observation],
            )

        @tool("inspect_query_result", description="按结果编号读取当前会话某次历史查询的具体数据行。")
        async def inspect_query_result(
            dataset_id: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            cursor: str | None = None,
            limit: int = 20,
        ) -> Command:
            if result_history is None:
                raise RuntimeError("历史结果服务未配置")
            offset = _decode_result_cursor(cursor, dataset_id)
            try:
                result = await result_history.inspect(
                    state["conversation_id"], dataset_id, max(offset, 0), min(max(limit, 1), 50)
                )
            except ResourceNotFoundError:
                observation = {
                    "tool": "inspect_query_result",
                    "ok": False,
                    "summary": "指定的历史查询结果不存在或不属于当前会话",
                    "error": "result_not_found",
                    "retryable": False,
                }
                return _command(
                    tool_call_id,
                    observation,
                    observations=[observation],
                )
            observation = {
                "tool": "inspect_query_result",
                "ok": True,
                "summary": f"读取结果 {dataset_id} 的 {result['returnedRows']} 行数据",
                "datasetId": dataset_id,
                "rowCount": result["rowCount"],
                "returnedRows": result["returnedRows"],
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview=result,
                    result_ref=f"result:{dataset_id}",
                    stats={
                        "rowCount": result["rowCount"],
                        "returnedRows": result["returnedRows"],
                    },
                    truncated=bool(result.get("hasMore") or result.get("truncated")),
                    next_cursor=(
                        _encode_result_cursor(
                            dataset_id,
                            result["offset"] + result["returnedRows"],
                        )
                        if result.get("hasMore")
                        else None
                    ),
                    available_actions=["inspect_query_result"],
                ),
                observations=[observation],
            )

        @tool(
            "analyze_dataframe",
            description="使用隔离的 Python 沙箱分析已有 SQL 结果，适用于聚类、预测等任务。",
        )
        async def analyze_dataframe(
            objective: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            dataset_ids: list[str] | None = None,
        ) -> Command:
            _progress("正在执行 Python 数据分析")
            if python_analysis is None or not retriever.settings.python_analysis_enabled:
                observation = {"tool": "analyze_dataframe", "ok": False, "error": "Python 分析未启用"}
                return _command(
                    tool_call_id,
                    observation,
                    observations=[observation],
                )

            try:
                analysis = await python_analysis.analyze(
                    run_id=state.get("run_id", "unknown"),
                    objective=objective,
                    query_results=state.get("query_results", []),
                    dataset_ids=dataset_ids,
                )
                observation = {
                    "tool": "analyze_dataframe",
                    "ok": True,
                    "summary": analysis["result"].get("summary", "Python 分析完成"),
                    "analysisId": analysis["id"],
                }
                return _command(
                    tool_call_id,
                    observation,
                    tool_content=build_tool_result(
                        observation,
                        preview=analysis["result"],
                        result_ref=f"artifact:{analysis['id']}",
                        stats={
                            "datasetIds": analysis.get("datasetIds", dataset_ids or []),
                        },
                    ),
                    python_analysis=analysis,
                    python_analyses=[*state.get("python_analyses", []), analysis],
                    observations=[observation],
                )
            except Exception as error:
                observation = {
                    "tool": "analyze_dataframe",
                    "ok": False,
                    "error": str(error),
                    "retryable": False,
                }
                return _command(
                    tool_call_id,
                    observation,
                    observations=[observation],
                )

        @tool(
            "rewrite_core_memory",
            description=(
                "仅当用户明确要求长期记住、修改或忘记某项跨会话偏好时调用。"
                "输入一条修改要求；工具会读取并整块改写当前核心记忆。一次性条件不要调用。"
            ),
        )
        async def rewrite_core_memory(
            instruction: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            if core_memory is None:
                raise RuntimeError("核心记忆服务未配置")
            async with session_factory() as session:
                result = await core_memory.rewrite(
                    repository=Repository(session),
                    instruction=instruction,
                    user_message=state.get("query", ""),
                )
            observation = {
                "tool": "rewrite_core_memory",
                "ok": True,
                "summary": result.get("summary") or ("核心记忆已更新" if result["changed"] else "核心记忆无需修改"),
                "changed": result["changed"],
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"memory": result["memory"]},
                    result_ref="memory:core",
                    stats={"changed": result["changed"]},
                    available_actions=["rewrite_core_memory"],
                ),
                observations=[observation],
            )

        tools = [
            update_analysis_plan,
            ask_clarification,
            search_schema,
            inspect_tables,
            retrieve_knowledge,
            execute_sql,
            search_history,
            inspect_query_result,
            read_conversation_context,
            analyze_dataframe,
        ]
        if core_memory is not None:
            tools.append(rewrite_core_memory)
        return tools

    def specifications(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "description": item.description,
                # tool_call_schema deliberately removes InjectedState and
                # InjectedToolCallId. Exposing args_schema makes the model echo the
                # entire LangGraph state back inside every tool call.
                "parameters": item.tool_call_schema.model_json_schema(),
                "execution": {
                    "readOnly": tool_metadata(item.name).read_only,
                    "concurrencySafe": tool_metadata(item.name).concurrency_safe,
                    "requiresConfirmation": tool_metadata(item.name).requires_confirmation,
                    "resultPersistence": tool_metadata(item.name).result_persistence,
                },
            }
            for item in self.tools
        ]


def _command(
    tool_call_id: str,
    observation: dict[str, Any],
    *,
    tool_content: dict[str, Any] | None = None,
    **updates: Any,
) -> Command:
    return Command(
        update={
            **updates,
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        tool_content or build_tool_result(observation),
                        ensure_ascii=False,
                        default=json_default,
                    ),
                    tool_call_id=tool_call_id,
                    id=f"tool-result-{tool_call_id}",
                )
            ],
        }
    )


def _successful_observation(
    state: AnalysisState,
    tool_name: str,
    query: str,
) -> dict[str, Any] | None:
    """查找同一 Run 中参数完全相同的成功只读检索，避免重复外部计算。"""
    normalized = " ".join(str(query).split()).casefold()
    for observation in reversed(state.get("observations", [])):
        if (
            observation.get("tool") == tool_name
            and observation.get("ok") is True
            and " ".join(str(observation.get("query", "")).split()).casefold() == normalized
        ):
            return observation
    return None


def _merge_history_matches(
    *,
    current_messages: list[dict[str, Any]],
    cross_messages: list[dict[str, Any]],
    result_matches: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """将异构历史来源按加权 RRF 融合为统一线索目录。

    各来源只使用自己的名次，不直接比较 FTS/BM25 原始分数。当前会话略微加权，
    跨会话结果略微降权，避免陈旧上下文压过用户刚刚讨论的内容。
    """
    ranked_sources = (
        ("current_message", current_messages, 1.1),
        ("query_result", result_matches, 1.0),
        ("cross_message", cross_messages, 0.9),
    )
    merged: dict[str, dict[str, Any]] = {}
    for source, items, weight in ranked_sources:
        for rank, item in enumerate(items, start=1):
            if source == "query_result":
                resource_id = str(item.get("datasetId") or "")
                if not resource_id:
                    continue
                ref = f"result:{resource_id}"
                normalized = {
                    "type": "query_result",
                    "ref": ref,
                    "datasetId": resource_id,
                    "title": item.get("question") or "历史查询结果",
                    "summary": item.get("sql") or "",
                    "metadata": {
                        "columns": item.get("columns", []),
                        "rowCount": item.get("rowCount"),
                        "createdAt": item.get("createdAt"),
                    },
                    "availableActions": ["inspect_query_result"],
                }
            else:
                resource_id = str(item.get("messageId") or "")
                if not resource_id:
                    continue
                ref = f"message:{resource_id}"
                normalized = {
                    "type": "conversation_message",
                    "ref": ref,
                    "messageId": resource_id,
                    "conversationId": item.get("conversationId"),
                    "title": item.get("title") or (
                        "当前会话消息" if source == "current_message" else "历史会话消息"
                    ),
                    "summary": item.get("snippet") or "",
                    "metadata": {
                        "role": item.get("role"),
                        "createdAt": item.get("createdAt"),
                        "scope": "current" if source == "current_message" else "all",
                    },
                    "availableActions": ["read_conversation_context"],
                }
            score = weight / (60 + rank)
            existing = merged.get(ref)
            if existing is None:
                normalized["_rrfScore"] = score
                merged[ref] = normalized
            else:
                existing["_rrfScore"] += score

    ordered = sorted(
        merged.values(),
        key=lambda item: (-float(item["_rrfScore"]), str(item["ref"])),
    )[:limit]
    for item in ordered:
        item.pop("_rrfScore", None)
    return ordered


def _encode_result_cursor(dataset_id: str, offset: int) -> str:
    """生成不可依赖内部格式的分页游标。"""
    payload = json.dumps(
        {"datasetId": dataset_id, "offset": max(offset, 0)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_result_cursor(cursor: str | None, dataset_id: str) -> int:
    """解析并校验分页游标，拒绝跨结果集复用或损坏的游标。"""
    if cursor is None or not cursor.strip():
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if payload.get("datasetId") != dataset_id:
            raise ValueError("分页游标不属于当前结果集")
        offset = int(payload["offset"])
        if offset < 0:
            raise ValueError("分页游标 offset 不能小于 0")
        return offset
    except (
        KeyError,
        TypeError,
        ValueError,
        binascii.Error,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as error:
        raise ValueError("分页游标格式无效") from error


def _compact_table(table: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": table.get("name"),
        "columns": [
            {
                "name": column.get("name"),
                "dataType": column.get("dataType"),
                "comment": column.get("comment", ""),
            }
            for column in table.get("columns", [])
        ],
        "foreignKeys": table.get("foreignKeys", []),
    }


def _progress(message: str) -> None:
    get_stream_writer()({"type": "stage.started", "stage": "tools", "message": message})


def _sql_event(event_type: str, data: dict[str, Any]) -> None:
    """发送 SQL 生命周期事件，由 Executor 持久化并通过 SSE 对外发布。"""
    get_stream_writer()(
        {
            "type": event_type,
            "stage": "tools",
            "data": data,
        }
    )

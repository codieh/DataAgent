"""分析 Agent 的工具集与工具节点。

``AnalysisToolRegistry`` 把数据库查询、Schema 检索、知识召回、历史结果读取、
Python 分析等业务能力封装成 LangGraph 工具；``LoggingToolNode`` 在工具执行
前后记录调用名称、入参与返回内容，便于观察 Agent 行为。
"""

import json
import logging
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, BaseTool, tool
from langgraph.config import get_stream_writer
from langgraph.prebuilt import InjectedState, ToolNode
from langgraph.types import Command, interrupt

from app.config import get_settings
from app.observability.logging_setup import truncate_text


logger = logging.getLogger(__name__)

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

        @tool("search_schema", description="检索完成当前分析问题所需的数据表及其字段和关联关系。")
        async def search_schema(
            query: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            _progress("正在检索相关数据表")
            previous = _successful_observation(state, "search_schema", query)
            if previous is not None and state.get("schema", {}).get("tables"):
                selected = list(state.get("selected_tables") or [])
                observation = {
                    "tool": "search_schema",
                    "ok": True,
                    "query": query,
                    "reused": True,
                    "summary": "相同 Schema 检索已成功完成，复用现有候选表，请继续下一步",
                    "tableNames": selected,
                }
                return _command(
                    tool_call_id,
                    observation,
                    tool_content=build_tool_result(
                        observation,
                        result_ref={
                            "type": "agent_state",
                            "path": "schema",
                            "scope": "current_run",
                            "readTool": "inspect_tables",
                        },
                        stats={"tableCount": len(selected), "tableNames": selected, "reused": True},
                    ),
                    observations=[observation],
                )
            full_schema = await database.schema_snapshot()
            recalled = await retriever.search_schema(query, full_schema)
            selected = [table["name"] for table in recalled["tables"]]
            observation = {
                "tool": "search_schema",
                "ok": bool(selected),
                "query": query,
                "summary": f"召回 {selected} 作为候选表",
                "tableNames": selected,
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"tables": recalled["tables"]},
                    result_ref={
                        "type": "agent_state",
                        "path": "schema",
                        "scope": "current_run",
                        "readTool": "inspect_tables",
                    },
                    stats={"tableCount": len(recalled["tables"]), "tableNames": selected},
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
                    result_ref={
                        "type": "agent_state",
                        "path": "schema",
                        "scope": "current_run",
                        "readTool": "inspect_tables",
                    },
                    stats={
                        "tableCount": len(inspected),
                        "tableNames": [table.get("name") for table in inspected],
                    },
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
                        result_ref={
                            "type": "agent_state",
                            "path": "knowledge",
                            "scope": "current_run",
                            "readTool": "retrieve_knowledge",
                        },
                        stats={
                            "documentCount": len(knowledge.get("documents", [])),
                            "evidenceCount": len(knowledge.get("evidences", [])),
                            "reused": True,
                        },
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
                    result_ref={
                        "type": "agent_state",
                        "path": "knowledge",
                        "scope": "current_run",
                        "readTool": "retrieve_knowledge",
                    },
                    stats={
                        "documentCount": len(knowledge["documents"]),
                        "evidenceCount": len(knowledge["evidences"]),
                    },
                ),
                knowledge=knowledge,
                observations=[observation],
            )

        @tool("execute_sql", description="安全校验并执行一条只读 MySQL SELECT，返回最终查询结果。")
        async def execute_sql(
            sql: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            """在一次原生工具调用内完成校验、审核和执行，只返回最终结果。"""
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
                    "reused": True,
                }
                return _command(
                    tool_call_id,
                    observation,
                    tool_content=build_tool_result(
                        observation,
                        result_ref={
                            "type": "query_result",
                            "datasetId": dataset_id,
                            "scope": "current_run",
                            "readTool": "inspect_query_result",
                        },
                        stats={
                            "rowCount": observation["rowCount"],
                            "datasetId": dataset_id,
                            "reused": True,
                        },
                    ),
                    sql=safe_sql,
                    sql_error=None,
                    safety=safety,
                    observations=[observation],
                )

            human_feedback = {"approved": True, "comment": ""}
            if state.get("human_review_enabled"):
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
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"columns": columns, "rows": preview},
                    result_ref={
                        "type": "query_result",
                        "datasetId": dataset["id"],
                        "scope": "current_run",
                        "readTool": "inspect_query_result",
                    },
                    stats={
                        "rowCount": len(rows),
                        "datasetId": dataset["id"],
                    },
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

        @tool("search_analysis_history", description="按问题、SQL 或字段关键词搜索当前会话以前产生的查询结果。")
        async def search_analysis_history(
            query: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            scope: str = "all",
            limit: int = 5,
        ) -> Command:
            if result_history is None:
                matches = []
            else:
                normalized_scope = scope if scope in {"query_results", "analyses", "all"} else "all"
                matches = await result_history.search(
                    state["conversation_id"], query, normalized_scope, min(max(limit, 1), 10)
                )
            observation = {
                "tool": "search_analysis_history",
                "ok": bool(matches),
                "summary": f"找到 {len(matches)} 个历史查询结果",
                "resultCount": len(matches),
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"matches": matches},
                    result_ref={
                        "type": "result_catalog",
                        "conversationId": state["conversation_id"],
                        "readTool": "inspect_query_result",
                    },
                    stats={"matchCount": len(matches)},
                ),
                observations=[observation],
            )

        @tool(
            "search_current_conversation",
            description="用户提到当前会话前面、之前、刚才说过的内容时，按关键词搜索本会话被摘要覆盖或不在近期窗口中的原始消息。",
        )
        async def search_current_conversation(
            query: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            limit: int = 5,
        ) -> Command:
            async with session_factory() as session:
                matches = await Repository(session).search_current_conversation_history(
                    state["conversation_id"],
                    query,
                    min(max(limit, 1), 10),
                    exclude_run_id=state.get("run_id"),
                )
            observation = {
                "tool": "search_current_conversation",
                "ok": bool(matches),
                "summary": f"在当前会话找到 {len(matches)} 条历史消息",
                "resultCount": len(matches),
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"matches": matches},
                    result_ref={
                        "type": "conversation_messages",
                        "conversationId": state["conversation_id"],
                        "readTool": "read_message_context",
                    },
                    stats={"matchCount": len(matches)},
                ),
                observations=[observation],
            )

        @tool(
            "read_message_context",
            description="根据 search_current_conversation 返回的消息编号，读取该消息及前后对话，恢复原始语境。",
        )
        async def read_message_context(
            message_id: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            before: int = 2,
            after: int = 2,
        ) -> Command:
            async with session_factory() as session:
                result = await Repository(session).read_message_context(
                    state["conversation_id"],
                    message_id,
                    min(max(before, 0), 10),
                    min(max(after, 0), 10),
                )
            observation = {
                "tool": "read_message_context",
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
                    result_ref={
                        "type": "conversation_messages",
                        "conversationId": state["conversation_id"],
                        "messageId": message_id,
                        "readTool": "read_message_context",
                    },
                    stats={"messageCount": len(result["messages"])},
                ),
                observations=[observation],
            )

        @tool(
            "search_conversation_history",
            description="用户明确提到其他会话或上一次会话时，按关键词搜索跨会话历史，返回候选会话目录。当前会话内查找应使用 search_current_conversation。",
        )
        async def search_conversation_history(
            query: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            limit: int = 5,
        ) -> Command:
            async with session_factory() as session:
                matches = await Repository(session).search_conversation_history(query, min(max(limit, 1), 10))
            observation = {
                "tool": "search_conversation_history",
                "ok": bool(matches),
                "summary": f"找到 {len(matches)} 个相关历史会话",
                "resultCount": len(matches),
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview={"matches": matches},
                    result_ref={
                        "type": "conversation_catalog",
                        "readTool": "read_conversation_history",
                    },
                    stats={"matchCount": len(matches)},
                ),
                observations=[observation],
            )

        @tool(
            "read_conversation_history",
            description="根据 search_conversation_history 返回的会话编号，读取该历史会话的具体消息。",
        )
        async def read_conversation_history(
            conversation_id: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            limit: int = 20,
        ) -> Command:
            async with session_factory() as session:
                result = await Repository(session).read_conversation_history(
                    conversation_id, min(max(limit, 1), 50)
                )
            observation = {
                "tool": "read_conversation_history",
                "ok": bool(result["messages"]),
                "summary": f"读取历史会话中的 {len(result['messages'])} 条消息",
                "conversationId": conversation_id,
            }
            return _command(
                tool_call_id,
                observation,
                tool_content=build_tool_result(
                    observation,
                    preview=result,
                    result_ref={
                        "type": "conversation_messages",
                        "conversationId": conversation_id,
                        "readTool": "read_conversation_history",
                    },
                    stats={"messageCount": len(result["messages"])},
                ),
                observations=[observation],
            )

        @tool("inspect_query_result", description="按结果编号读取当前会话某次历史查询的具体数据行。")
        async def inspect_query_result(
            dataset_id: str,
            state: Annotated[AnalysisState, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
            offset: int = 0,
            limit: int = 20,
        ) -> Command:
            if result_history is None:
                raise RuntimeError("历史结果服务未配置")
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
                    result_ref={
                        "type": "result_set",
                        "datasetId": dataset_id,
                        "conversationId": state["conversation_id"],
                        "readTool": "inspect_query_result",
                    },
                    stats={
                        "rowCount": result["rowCount"],
                        "returnedRows": result["returnedRows"],
                    },
                    truncated=bool(result.get("hasMore") or result.get("truncated")),
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
                        result_ref={
                            "type": "analysis_artifact",
                            "analysisId": analysis["id"],
                            "scope": "current_run",
                        },
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
                    result_ref={"type": "core_memory", "scope": "cross_conversation"},
                    stats={"changed": result["changed"]},
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
            search_analysis_history,
            inspect_query_result,
            search_current_conversation,
            read_message_context,
            search_conversation_history,
            read_conversation_history,
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
            }
            for item in self.tools
        ]


class LoggingToolNode(ToolNode):
    """LangGraph ``ToolNode`` 的子类，在工具执行前后统一记录调用情况。

    它在不改变任何工具行为的前提下，于两个时机写入日志：

    - 执行前：记录模型决定调用的工具名称与入参（``args``），便于确认 Agent
      的每一步决策。
    - 执行后：记录工具返回的内容（即写回上下文的 ``ToolMessage``），便于确认
      工具实际返回了什么（召回了哪些表、SQL 是否成功、Python 分析结论等）。

    日志内容会被截断，避免超大的工具结果（如整张表的预览）刷屏。
    """

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        settings = get_settings()
        # 执行前：记录每个待执行工具调用的名称与入参。
        for call in self._last_tool_calls(input):
            name = call.get("name")
            args = call.get("args", {})
            logger.info(
                "tool call started: name=%s args=%s",
                name,
                truncate_text(json.dumps(args, ensure_ascii=False), settings.tool_log_content_chars),
            )
        # 执行工具（保持父类行为完全不变）。
        result = await super().ainvoke(input, config, **kwargs)
        # 执行后：记录每个工具返回的内容（observation）。
        # 普通工具返回 {"messages": [...]}；本项目工具返回 Command，其更新内容
        # 在 command.update["messages"] 里。两种形态都兼容提取。
        result_items = result if isinstance(result, list) else [result]
        for item in result_items:
            messages: list[Any] = []
            if isinstance(item, dict):
                messages = item.get("messages", []) or []
            elif isinstance(item, Command):
                messages = (getattr(item, "update", None) or {}).get("messages", []) or []
            for message in messages:
                content = getattr(message, "content", "")
                logger.info(
                    "tool call completed: content=%s",
                    truncate_text(str(content), settings.tool_log_content_chars),
                )
        return result

    @staticmethod
    def _last_tool_calls(input: Any) -> list[dict[str, Any]]:
        """从 LangGraph 传入的状态中提取最后一条 AI 消息里的工具调用。"""
        if not isinstance(input, dict):
            return []
        messages = input.get("messages", []) or []
        if not messages:
            return []
        last = messages[-1]
        return getattr(last, "tool_calls", None) or []


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

"""面向模型的有界上下文构建器。

工作流的持久状态（``AnalysisState``）往往很大（含完整 schema、知识库、历史消息等），
无法直接全部喂给模型。本模块把状态“投影”为一个可控大小的上下文 ``AgentContext``：
- 只保留当前轮决策需要的字段（query、memory、plan、budgets、schema、knowledge……）；
- 对 schema 与 knowledge 按 token 预算做裁剪（见 ``_budget_schema`` / ``_budget_knowledge``）；
- 把体积庞大的工具消息（如 search_schema 的返回）压缩为摘要，只保留表格清单与状态标记；
- 统计估算 token 数，供上层监控上下文占用。
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from langchain_core.messages import AnyMessage, ToolMessage

from app.config import Settings
from app.context import estimate_tokens
from app.workflow.state import AnalysisState


@dataclass(frozen=True)
class AgentContext:
    """一次模型调用所需的完整上下文快照。

    属性：
        payload: 结构化上下文（最终会被序列化为 JSON 作为 user 消息内容）。
        messages: 传给 LLM 的消息列表（对话历史 + 当前上下文 + 投影后的工具消息）。
        stats: 统计信息，目前包含 ``estimatedTokens``（上下文估算 token 数）与
            ``compactedToolMessages``（被压缩的工具消息条数）。
    """

    payload: dict[str, Any]
    messages: list[Any]
    stats: dict[str, int]


class AgentContextBuilder:
    """把持久化的工作流状态投影为面向单一模型调用的有界上下文。

    关键设计：
    - 不直接暴露全部历史消息，而是从 ``memory_context`` 取近轮对话，并追加当前上下文；
    - 工具消息按类型压缩，避免把完整表结构/查询结果重复塞进上下文；
    - 对 schema 与 knowledge 施加 token 预算，保证上下文长度可控。
    """

    def __init__(self, settings: Settings, result_history):
        self.settings = settings
        self.result_history = result_history

    async def build(self, state: AnalysisState) -> AgentContext:
        # 取最近一次查询结果作为“当前/活动结果”，供模型参考最新数据
        active_ref = (state.get("query_results") or [])[-1] if state.get("query_results") else None
        active_result = None
        if active_ref and active_ref.get("datasetId"):
            # 读取活动结果的预览行（受配置限制行数），并把原始 SQL 一并回挂
            active_result = await self.result_history.inspect(
                state["conversation_id"],
                active_ref["datasetId"],
                0,
                self.settings.context_result_preview_rows,
            )
            active_result["sql"] = active_ref.get("sql")
        # 取会话下最近的结果目录（用于“可用结果”清单），限制条数控制上下文体积
        recent = await self.result_history.recent(
            state["conversation_id"], self.settings.context_result_catalog_limit
        )
        active_id = active_ref.get("datasetId") if active_ref else None
        # 从最近结果中排除当前活动结果，避免重复
        available = [item for item in recent if item.get("datasetId") != active_id]
        payload = {
            # 优先使用“已结合上下文消歧”后的查询，否则退回原始查询
            "query": state.get("contextualized_query") or state["query"],
            "memory": _supplemental_memory(state),
            "plan": state.get("plan"),
            # iteration 从 1 开始计数，便于模型理解当前是第几轮决策
            "iteration": state.get("agent_iterations", 0) + 1,
            "budgets": {
                # 把“剩余可用次数”显式告知模型，使其能感知预算边界
                "maxIterations": self.settings.agent_max_iterations,
                "schemaSearchesRemaining": max(0, self.settings.agent_max_schema_searches - state.get("schema_search_count", 0)),
                "sqlExecutionsRemaining": max(0, self.settings.agent_max_sql_executions - state.get("sql_execution_count", 0)),
            },
            # 对 schema / knowledge 按 token 预算裁剪，避免上下文溢出
            "schema": _budget_schema(state.get("schema", {}), self.settings.context_schema_token_budget),
            "knowledge": _budget_knowledge(state.get("knowledge", {}), self.settings.context_knowledge_token_budget),
            "activeResult": active_result,
            "availableResults": available,
            # 只取最近 8 条“观察”并按白名单压缩，控制上下文体积
            "observations": [_compact_observation(item) for item in state.get("observations", [])[-8:]],
            "pythonAnalyses": [item.get("result", {}) for item in state.get("python_analyses", [])],
        }
        # 由近轮对话历史 + 当前上下文字符串拼装模型消息列表
        messages = [*_conversation_messages(state, json.dumps(payload, ensure_ascii=False, default=_json_default))]
        # 投影（压缩）工具消息，并记录被压缩的条数
        projected, compacted = _project_tool_messages(state.get("messages", []))
        messages.extend(projected)
        serialized = json.dumps(payload, ensure_ascii=False, default=_json_default)
        return AgentContext(
            payload=payload,
            messages=messages,
            # 估算上下文 token 数，供上层监控；compactedToolMessages 反映压缩力度
            stats={"estimatedTokens": estimate_tokens(serialized), "compactedToolMessages": compacted},
        )


def _project_tool_messages(messages: list[AnyMessage]) -> tuple[list[AnyMessage], int]:
    """把体积庞大的工具消息压缩为摘要，返回（投影后消息列表, 被压缩条数）。

    仅对 ``search_schema`` / ``inspect_tables`` 这类会返回完整表结构的工具消息做压缩：
    丢弃列定义等细节，只保留 ``tableNames``、摘要与指向 ``state.schema`` 的引用，
    既保留“模型已检索过哪些表”的事实，又避免重复占用上下文。其它工具消息原样保留。
    """
    result = []
    compacted = 0
    for message in messages:
        if not isinstance(message, ToolMessage):
            result.append(message)
            continue
        try:
            content = json.loads(str(message.content))
        except (TypeError, json.JSONDecodeError):
            # 非 JSON（纯文本）工具消息无法压缩，原样保留
            result.append(message)
            continue
        if content.get("tool") in {"search_schema", "inspect_tables"} or "tables" in content:
            # 提取表名清单：优先用 tableNames，其次从 tables 列表中取 name
            names = content.get("tableNames") or [item.get("name") for item in content.get("tables", [])]
            content = {
                "ok": content.get("ok", True),
                "summary": content.get("summary", "表结构已载入"),
                "tableNames": [name for name in names if name],
                # 指向状态中的完整 schema，模型需要时按表名引用
                "schemaRef": "state.schema",
            }
            result.append(ToolMessage(content=json.dumps(content, ensure_ascii=False), tool_call_id=message.tool_call_id))
            compacted += 1
        else:
            result.append(message)
    return result, compacted


def _compact_observation(item: dict[str, Any]) -> dict[str, Any]:
    """只保留观察对象中的白名单字段，丢弃冗余细节以控制上下文体积。"""
    allowed = {"tool", "ok", "summary", "error", "retryable", "resultMode", "datasetId", "rowCount", "returnedRows", "tableNames"}
    return {key: value for key, value in item.items() if key in allowed}


def _conversation_messages(state: AnalysisState, current_content: str) -> list[dict[str, str]]:
    """由近轮对话历史组装模型消息列表，末尾追加当前上下文（user 消息）。

    过滤掉 system 之外的非法角色，只保留有内容的 system/user/assistant 消息，
    并把当前结构化上下文作为一条 user 消息追加到最后。
    """
    messages = []
    for item in state.get("memory_context", {}).get("recentMessages", []):
        role, content = str(item.get("role") or ""), str(item.get("content") or "")
        if role in {"system", "user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": current_content})
    return messages


def _supplemental_memory(state: AnalysisState) -> dict[str, Any]:
    """从 ``memory_context`` 中提取补充记忆（摘要、相关消息、长期记忆）。"""
    context = state.get("memory_context", {})
    return {"summary": context.get("summary", ""), "relatedMessages": context.get("relatedMessages", []), "longTermMemories": context.get("longTermMemories", [])}


def _budget_schema(schema: dict[str, Any], budget: int) -> dict[str, Any]:
    """按 token 预算裁剪 schema：逐表、逐列累加估算 token，超预算即停止。

    设计要点：
    - 列按出现顺序累加，一旦 ``used + cost > budget`` 立即停止把该表剩余列纳入；
    - 若预算已耗尽（``used >= budget``）则连后续表也不再处理；
    - 这只是“上下文投影”的裁剪，完整 schema 仍保存在工作流状态中。
    """
    selected, used = [], 0
    for table in schema.get("tables", []):
        compact = {**table, "columns": []}
        for column in table.get("columns", []):
            cost = estimate_tokens(json.dumps(column, ensure_ascii=False, default=_json_default))
            if used + cost > budget:
                break
            compact["columns"].append(column)
            used += cost
        selected.append(compact)
        if used >= budget:
            break
    return {"tables": selected}


def _budget_knowledge(knowledge: dict[str, Any], budget: int) -> dict[str, Any]:
    """按 token 预算裁剪知识库：先放 evidences 再放 documents（优先级由调用顺序决定）。

    超过预算的条目直接跳过（continue），不会部分截取，保证每个条目完整。
    """
    result, used = {"documents": [], "evidences": []}, 0
    for kind in ("evidences", "documents"):
        for item in knowledge.get(kind, []):
            cost = estimate_tokens(json.dumps(item, ensure_ascii=False, default=_json_default))
            if used + cost <= budget:
                result[kind].append(item)
                used += cost
    return result


def _json_default(value: Any) -> Any:
    """``json.dumps`` 的兜底序列化：把日期/Decimal/字节转换为可序列化形式。

    未知类型仍抛 ``TypeError``，由调用方保证传入数据可序列化。
    """
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

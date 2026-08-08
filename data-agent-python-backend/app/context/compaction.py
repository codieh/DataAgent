"""上下文压缩（compaction）。

在把消息列表送入大模型前，对体积不可控的内容（尤其是工具返回结果）进行裁剪，
避免临时性的大负载把上下文窗口耗尽。本模块提供两条能力：
- message_tokens：估算整条消息（含工具调用元数据）的 token 数。
- trim_tool_results：对超长工具结果做结构化裁剪，始终保持合法 JSON。
"""

import json
from typing import Any

from app.context.tokens import estimate_tokens, truncate_to_tokens


def message_tokens(message: dict[str, Any]) -> int:
    """估算整条线消息的 token 数，包含工具调用等元数据。"""
    # 先序列化为线格式再统一估算，确保工具调用参数等附加字段也被计入。
    return estimate_tokens(json.dumps(message, ensure_ascii=False, default=str))


def trim_tool_results(messages: list[dict[str, Any]], token_limit: int) -> list[dict[str, Any]]:
    """在工具结果撑爆上下文窗口前，对其内容进行截断。

    参数:
        messages: 待处理的消息列表。
        token_limit: 单条工具消息允许保留的 token 上限。
    返回:
        裁剪后的消息列表：非工具消息或长度未超限者原样保留；超长结果保留
        工具元数据、读取引用和一段真实预览，不会从 JSON 中间切断。
    """
    trimmed: list[dict[str, Any]] = []
    for message in messages:
        # 仅对超长的 tool 角色消息做截断，其它消息（含正常工具消息）直接保留。
        if message.get("role") != "tool" or estimate_tokens(str(message.get("content", ""))) <= token_limit:
            trimmed.append(message)
            continue
        trimmed.append(
            {
                **message,
                "content": _trim_tool_content(str(message.get("content", "")), token_limit),
            }
        )
    return trimmed


def compact_old_tool_results(
    messages: list[dict[str, Any]],
    *,
    compact_tokens: int,
) -> tuple[list[dict[str, Any]], int]:
    """压缩所有超过目标大小的 ToolMessage，不保护最近一次工具结果。

    该操作只在请求上下文达到压缩阈值后执行。它不删除 ToolMessage，因此仍能保持
    assistant.tool_calls 与 tool_call_id 的协议配对；只缩短结果正文，避免当前
    Run 的工具轨迹持续挤占上下文。
    """
    tool_indexes = [index for index, message in enumerate(messages) if message.get("role") == "tool"]
    compacted = list(messages)
    compacted_count = 0
    for index in tool_indexes:
        content = str(messages[index].get("content", ""))
        if estimate_tokens(content) <= compact_tokens:
            continue
        compressed_content = _compact_old_tool_content(content, compact_tokens)
        if estimate_tokens(compressed_content) >= estimate_tokens(content):
            continue
        compacted[index] = {
            **messages[index],
            "content": compressed_content,
        }
        compacted_count += 1
    return compacted, compacted_count


_METADATA_KEYS = (
    "tool",
    "ok",
    "summary",
    "error",
    "retryable",
    "resultMode",
    "resultRef",
    "nextCursor",
    "availableActions",
    "nextCursor",
    "availableActions",
    "stats",
    "datasetId",
    "rowCount",
    "returnedRows",
)


def _trim_tool_content(content: str, token_limit: int) -> str:
    """把单条超长工具结果转换为合法 JSON，并保留有界的真实内容前缀。"""
    parsed = _parse_object(content)
    if parsed is None:
        return json.dumps(
            {
                "previewText": truncate_to_tokens(content, max(1, token_limit - 20)),
                "truncated": True,
                "notice": "工具结果过长，已截断",
            },
            ensure_ascii=False,
        )

    compact = _metadata(parsed)
    source = parsed.get("preview", parsed)
    overhead = estimate_tokens(json.dumps(compact, ensure_ascii=False, default=str))
    preview_budget = max(1, token_limit - overhead - 24)
    compact["previewText"] = truncate_to_tokens(
        json.dumps(source, ensure_ascii=False, default=str),
        preview_budget,
    )
    compact["truncated"] = True
    compact["notice"] = "工具结果过长，已截断；可根据 resultRef 和 availableActions 继续读取"
    return json.dumps(compact, ensure_ascii=False, default=str)


def trim_tool_content(content: str, token_limit: int) -> str:
    """公开的单条工具结果结构化裁剪入口，供活动上下文管理器复用。"""
    return _trim_tool_content(content, token_limit)


def _compact_old_tool_content(content: str, token_limit: int) -> str:
    """将旧结果降级为目录项，不破坏 tool_call_id 配对和 JSON 结构。"""
    parsed = _parse_object(content)
    if parsed is None:
        return json.dumps(
            {
                "previewText": truncate_to_tokens(content, max(1, token_limit - 24)),
                "truncated": True,
                "compacted": True,
                "notice": "较早工具结果因上下文压力已压缩",
            },
            ensure_ascii=False,
        )

    compact = _metadata(parsed)
    compact["truncated"] = bool(parsed.get("truncated")) or "preview" in parsed
    compact["compacted"] = True
    compact["notice"] = "较早工具结果已降级为目录；按 resultRef 和 availableActions 获取详情"
    serialized = json.dumps(compact, ensure_ascii=False, default=str)
    if estimate_tokens(serialized) <= token_limit:
        return serialized
    return _trim_tool_content(serialized, token_limit)


def snip_tool_content(content: str, token_limit: int) -> str:
    """把工具结果降级为可回读的目录项，不调用模型。"""
    return _compact_old_tool_content(content, token_limit)


def _parse_object(content: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _metadata(content: dict[str, Any]) -> dict[str, Any]:
    return {key: content[key] for key in _METADATA_KEYS if key in content}

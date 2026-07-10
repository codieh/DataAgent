"""上下文压缩（compaction）。

在把消息列表送入大模型前，对体积不可控的内容（尤其是工具返回结果）进行裁剪，
避免临时性的大负载把上下文窗口耗尽。本模块提供两条能力：
- message_tokens：估算整条消息（含工具调用元数据）的 token 数。
- trim_tool_results：对超长的工具结果消息做截断并加注提示。
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
        裁剪后的消息列表：非工具消息或长度未超限者原样保留，超长者被截断
        并在末尾追加「已截断」提示，保留其余字段。
    """
    trimmed: list[dict[str, Any]] = []
    for message in messages:
        # 仅对超长的 tool 角色消息做截断，其它消息（含正常工具消息）直接保留。
        if message.get("role") != "tool" or estimate_tokens(str(message.get("content", ""))) <= token_limit:
            trimmed.append(message)
            continue
        # 在 token 预算内保留前缀，并明确告知模型该结果因过长被截断。
        prefix = truncate_to_tokens(str(message.get("content", "")), token_limit)
        trimmed.append({**message, "content": f"{prefix}\n[工具结果过长，已截断]"})
    return trimmed

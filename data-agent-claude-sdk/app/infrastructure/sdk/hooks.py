"""SDK Hook：把工具调用、压缩和失败事件写入应用事件流。"""

from typing import Any

from app.application.events import EventBroker
from app.domain.models import TenantContext
from app.infrastructure.persistence.database import ControlDatabase

try:
    from claude_agent_sdk import HookMatcher
except ImportError:  # pragma: no cover
    HookMatcher = None


def build_hooks(context: TenantContext, events: EventBroker, control: ControlDatabase) -> dict[str, list[Any]]:
    if HookMatcher is None:
        raise RuntimeError("未安装 claude-agent-sdk，无法创建 Hooks")

    inputs: dict[str, dict[str, Any]] = {}

    def call_key(input_data: Any, tool_use_id: str | None) -> str:
        return tool_use_id or f"generated-{id(input_data)}"

    async def pre_tool(input_data: Any, tool_use_id: str | None, _hook_context: Any) -> dict[str, Any]:
        tool_name = str(input_data.get("tool_name", "unknown"))
        key = call_key(input_data, tool_use_id)
        inputs[key] = dict(input_data.get("tool_input", {}))
        await events.publish(
            context,
            "tool.requested",
            {"tool_name": tool_name, "tool_use_id": tool_use_id, "input": input_data.get("tool_input", {})},
        )
        await control.append_tool_call(
            context,
            key,
            tool_name,
            input_data.get("tool_input", {}),
            None,
            "requested",
        )
        return {}

    async def post_tool(input_data: Any, tool_use_id: str | None, _hook_context: Any) -> dict[str, Any]:
        await events.publish(
            context,
            "tool.completed",
            {
                "tool_name": input_data.get("tool_name", "unknown"),
                "tool_use_id": tool_use_id,
                "output": input_data.get("tool_response"),
            },
        )
        key = call_key(input_data, tool_use_id)
        await control.append_tool_call(
            context,
            key,
            str(input_data.get("tool_name", "unknown")),
            inputs.pop(key, {}),
            {"tool_response": input_data.get("tool_response")},
            "completed",
        )
        return {}

    async def failed_tool(input_data: Any, tool_use_id: str | None, _hook_context: Any) -> dict[str, Any]:
        await events.publish(
            context,
            "tool.failed",
            {
                "tool_name": input_data.get("tool_name", "unknown"),
                "tool_use_id": tool_use_id,
                "error": input_data.get("error") or input_data.get("tool_response"),
            },
        )
        key = call_key(input_data, tool_use_id)
        await control.append_tool_call(
            context,
            key,
            str(input_data.get("tool_name", "unknown")),
            inputs.pop(key, {}),
            None,
            "failed",
            str(input_data.get("error") or input_data.get("tool_response") or "tool failed"),
        )
        return {}

    async def pre_compact(input_data: Any, _tool_use_id: str | None, _hook_context: Any) -> dict[str, Any]:
        await events.publish(context, "context.compaction.started", {"input": input_data})
        return {}

    return {
        "PreToolUse": [HookMatcher(matcher="^mcp__data_agent__", hooks=[pre_tool])],
        "PostToolUse": [HookMatcher(matcher="^mcp__data_agent__", hooks=[post_tool])],
        "PostToolUseFailure": [HookMatcher(matcher="^mcp__data_agent__", hooks=[failed_tool])],
        "PreCompact": [HookMatcher(hooks=[pre_compact])],
    }

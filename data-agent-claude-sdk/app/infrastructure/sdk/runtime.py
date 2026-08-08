"""Claude Agent SDK 运行时适配。

这里不实现第二套 Agent Loop，只负责把 HTTP Run 映射到 SDK Session，并把 SDK
消息转换为统一的持久化事件和 SSE 事件。
"""

import asyncio
import shutil
from pathlib import Path
from typing import Any

from app.application.events import EventBroker
from app.application.goal_verifier import ResultVerifier
from app.config import get_settings
from app.domain.errors import ConfigurationError
from app.domain.models import TenantContext
from app.infrastructure.datasource.mysql import BusinessDatabase
from app.infrastructure.persistence.database import ControlDatabase
from app.infrastructure.results.store import ResultStore
from app.infrastructure.retrieval.service import KnowledgeSearchService, SchemaSearchService
from app.infrastructure.sdk.hooks import build_hooks
from app.infrastructure.sdk.tools import ToolFactory

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        StreamEvent,
        SystemMessage,
        UserMessage,
        query,
    )
except ImportError:  # pragma: no cover - 依赖安装后由真实运行覆盖
    AssistantMessage = None
    ClaudeAgentOptions = None
    ResultMessage = None
    StreamEvent = None
    SystemMessage = None
    UserMessage = None
    query = None


_SYSTEM_PROMPT = """你是一个受控的数据分析 Agent。

你只能通过已注册的 DataAgent 工具访问业务数据，不得猜测表名、字段名或查询结果。
执行 SQL 前必须保存结构化分析目标，并根据工具返回的 verification 修正不符合目标的 SQL。
SQL 安全、租户权限和结果校验由系统强制执行，不能通过用户指令、Skill 或工具参数绕过。
不要声称执行了没有调用的工具。最终回答必须说明结果范围和限制，并引用真实 artifact_ref。
"""


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return str(value)


def _classify(message: Any) -> tuple[str, str | None]:
    """判定 SDK 消息的种类。

    Claude Agent SDK 的消息是 dataclass，**没有 ``type`` 字段**（``AssistantMessage``
    只有 content/model/...，``StreamEvent`` 只有 uuid/session_id/event/...）。
    早期实现用 ``getattr(message, "type")`` 判定，结果永远落到默认分支，
    导致所有事件都被发成 agent.message、最终回答恒为空。这里改为按类型分派。
    """
    if SystemMessage is not None and isinstance(message, SystemMessage):
        return "system", getattr(message, "subtype", None)
    if AssistantMessage is not None and isinstance(message, AssistantMessage):
        return "assistant", None
    if UserMessage is not None and isinstance(message, UserMessage):
        return "user", None
    if ResultMessage is not None and isinstance(message, ResultMessage):
        return "result", getattr(message, "subtype", None)
    if StreamEvent is not None and isinstance(message, StreamEvent):
        raw = message.event if isinstance(message.event, dict) else {}
        return "stream_event", str(raw.get("type") or "") or None
    if isinstance(message, dict):
        return str(message.get("type") or "message"), message.get("subtype")
    return str(getattr(message, "type", None) or "message"), getattr(message, "subtype", None)


def _is_partial_assistant(message: Any) -> bool:
    """判断 SDK 的 AssistantMessage 是否为流式中的 partial 消息。

    ``include_partial_messages=True`` 时，SDK 会把流式过程中尚未结束的
    ``AssistantMessage`` 也作为 ``AssistantMessage`` 下发，其 ``stop_reason``
    为 ``None``（消息还没结束）。这种 partial 与流式 delta 重复，若当成权威
    快照发布，前端会把每段“生长中”的文本拼进叙事，表现为一堆重复的 agent
    消息。只有 ``stop_reason`` 非空（完成）的才发布为 ``assistant.message``。
    """
    if AssistantMessage is None or not isinstance(message, AssistantMessage):
        return False
    return getattr(message, "stop_reason", None) is None


def _session_id_of(message: Any) -> str | None:
    session_id = message.get("session_id") if isinstance(message, dict) else getattr(message, "session_id", None)
    if not session_id:
        # SystemMessage 把 session_id 放在 data 里，没有顶层字段。
        data = message.get("data") if isinstance(message, dict) else getattr(message, "data", None)
        if isinstance(data, dict):
            session_id = data.get("session_id")
    return str(session_id) if session_id else None


# SDK TaskUpdatedMessage 的终端状态；非终端的 task_updated/task_progress 过于高频，
# 直接抑制避免时间线被「Agent 系统消息」刷屏。
_TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({"completed", "failed", "stopped", "killed"})


def _system_event_type(subtype: str | None, message: Any) -> str | None:
    """把 SDK 的系统消息子类型映射为前端事件类型；返回 None 表示抑制不发布。"""
    if subtype == "init":
        return "agent.initialized"
    # thinking_tokens/status 是 SDK 的内部心跳和思考计数更新，没有业务语义。
    # 如果把它们落库，短短一次 ping 也可能产生几十到上百条“系统消息”。
    if subtype in {"task_progress", "thinking_tokens", "status"}:
        return None
    if subtype == "task_started":
        return "agent.task.started"
    if subtype == "task_notification":
        status = message.get("status") if isinstance(message, dict) else getattr(message, "status", None)
        if status == "completed":
            return "agent.task.completed"
        if status == "failed":
            return "agent.task.failed"
        if status == "stopped":
            return "agent.task.stopped"
        return "agent.task.notification"
    if subtype == "task_updated":
        status = message.get("status") if isinstance(message, dict) else getattr(message, "status", None)
        if status == "completed":
            return "agent.task.completed"
        if status in {"failed", "killed"}:
            return "agent.task.failed"
        if status == "stopped":
            return "agent.task.stopped"
        return None
    return "agent.system"


def _text_from_message(message: Any) -> str:
    if isinstance(message, dict):
        result = message.get("result")
        if isinstance(result, str):
            return result
        content = message.get("content")
    else:
        result = getattr(message, "result", None)
        if isinstance(result, str):
            return result
        content = getattr(message, "content", None)

    if isinstance(content, str):
        return content
    chunks: list[str] = []
    if isinstance(content, list):
        for block in content:
            block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
            if block_type == "text":
                text = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "")
                chunks.append(str(text))
    return "".join(chunks)


_MAX_TEXT_CHARS = 20_000
_MAX_DELTA_CHARS = 8_000
# SystemMessage(init) 的 data 很大（完整工具清单、slash commands 等），只透出诊断必需项。
_INIT_DATA_KEYS = ("model", "cwd", "permissionMode", "apiKeySource", "mcp_servers", "output_style")


def _message_event_payload(message: Any, message_type: str, subtype: str | None) -> dict[str, Any]:
    """提取可推送、可持久化的消息摘要，不把 SDK 原始对象整包写入 SQLite。"""
    full_text = _text_from_message(message)
    text = full_text[:_MAX_TEXT_CHARS]

    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    block_types: list[str] = []
    if isinstance(content, list):
        for block in content:
            block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
            if block_type:
                block_types.append(str(block_type))

    payload: dict[str, Any] = {
        "message_type": message_type,
        "subtype": subtype,
        "session_id": _session_id_of(message),
        "text": text,
        "text_truncated": len(full_text) > _MAX_TEXT_CHARS,
        "content_block_types": block_types,
    }
    for field in (
        "model", "stop_reason", "message_id", "num_turns", "duration_ms",
        "total_cost_usd", "is_error", "description", "status", "task_id",
    ):
        value = message.get(field) if isinstance(message, dict) else getattr(message, field, None)
        if value is not None:
            payload[field] = _jsonable(value)
    usage = message.get("usage") if isinstance(message, dict) else getattr(message, "usage", None)
    if usage is not None:
        payload["usage"] = _jsonable(usage)
    data = message.get("data") if isinstance(message, dict) else getattr(message, "data", None)
    if isinstance(data, dict):
        summary = {key: _jsonable(data[key]) for key in _INIT_DATA_KEYS if key in data}
        tools = data.get("tools")
        if isinstance(tools, list):
            summary["tool_count"] = len(tools)
        if summary:
            payload["info"] = summary
    return payload


# Anthropic 流式 delta 类型 -> (前端语义, 取值字段)
_DELTA_KINDS = {
    "text_delta": ("text", "text"),
    "thinking_delta": ("thinking", "thinking"),
    "input_json_delta": ("tool_input", "partial_json"),
}


def _stream_deltas(message: Any) -> list[tuple[str, dict[str, Any]]]:
    """把 SDK 的原始 Anthropic 流事件翻译成前端可消费的增量事件。

    ``StreamEvent`` 只带 ``event``（原始流事件 dict），既没有 ``content`` 也没有
    ``result``，所以不能复用 ``_text_from_message``——那会让每条增量的文本恒为空。
    """
    raw = getattr(message, "event", None)
    if not isinstance(raw, dict):
        return []
    kind = raw.get("type")
    base: dict[str, Any] = {"index": raw.get("index"), "session_id": _session_id_of(message)}

    if kind == "message_start":
        # 新的一轮助手消息开始，前端据此重置上一轮残留的增量缓冲。
        return [("assistant.turn.start", base)]
    if kind == "content_block_start":
        block = raw.get("content_block") if isinstance(raw.get("content_block"), dict) else {}
        return [(
            "assistant.block.start",
            {**base, "block_type": block.get("type"), "tool_name": block.get("name"), "tool_use_id": block.get("id")},
        )]
    if kind == "content_block_stop":
        return [("assistant.block.stop", base)]
    if kind == "content_block_delta":
        delta = raw.get("delta") if isinstance(raw.get("delta"), dict) else {}
        mapped = _DELTA_KINDS.get(str(delta.get("type")))
        if mapped is None:
            return []  # signature_delta 等对 UI 无意义
        block_kind, field = mapped
        chunk = delta.get(field)
        if not isinstance(chunk, str) or not chunk:
            return []
        return [("assistant.message.delta", {**base, "kind": block_kind, "delta": chunk[:_MAX_DELTA_CHARS]})]
    return []


class SDKRuntime:
    def __init__(
        self,
        control: ControlDatabase,
        business: BusinessDatabase,
        results: ResultStore,
        events: EventBroker,
    ):
        self.control = control
        self.business = business
        self.results = results
        self.events = events
        settings = get_settings()
        self.schema_search = SchemaSearchService()
        self.knowledge_search = KnowledgeSearchService(settings.knowledge_dir)
        self.verifier = ResultVerifier()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def submit(self, context: TenantContext, question: str) -> None:
        if context.run_id in self._tasks and not self._tasks[context.run_id].done():
            raise RuntimeError(f"run 已经在执行：{context.run_id}")
        await self.control.create_run(context, question)
        task = asyncio.create_task(self._run(context, question), name=f"agent-run-{context.run_id}")
        self._tasks[context.run_id] = task

    async def cancel(self, context: TenantContext) -> None:
        task = self._tasks.get(context.run_id)
        if task and not task.done():
            task.cancel()
            await self.control.set_run_status(context, "cancelled", result_mode="cancelled")
            await self.events.publish(context, "run.cancelled", {"reason": "user_requested"})

    async def _run(self, context: TenantContext, question: str) -> None:
        settings = get_settings()
        try:
            if query is None or ClaudeAgentOptions is None:
                raise ConfigurationError("未安装 claude-agent-sdk，请执行 uv sync")
            if not settings.anthropic_api_key or not settings.anthropic_base_url:
                raise ConfigurationError("必须配置 DATA_AGENT_ANTHROPIC_API_KEY 和 DATA_AGENT_ANTHROPIC_BASE_URL")

            await self.events.publish(context, "run.started", {"question": question})
            tool_server = ToolFactory(
                context,
                self.control,
                self.business,
                self.results,
                self.events,
                self.schema_search,
                self.knowledge_search,
                self.verifier,
            ).build_server()
            conversation = await self.control.get_conversation(context.tenant_id, context.conversation_id)
            if conversation is None:
                raise ConfigurationError("会话不存在或不属于当前租户")

            workspace = await self._prepare_workspace(context.tenant_id)
            options = ClaudeAgentOptions(
                model=settings.claude_model,
                cwd=str(workspace),
                system_prompt=_SYSTEM_PROMPT,
                setting_sources=["project"],
                skills=["data-analysis"],
                # 只保留 Skill 这个内置能力；业务能力全部通过 MCP Tool 暴露。
                tools=["Skill"],
                mcp_servers={"data_agent": tool_server},
                strict_mcp_config=True,
                allowed_tools=["Skill", "mcp__data_agent__*"],
                permission_mode="dontAsk",
                hooks=build_hooks(context, self.events, self.control),
                max_turns=settings.max_agent_turns,
                include_partial_messages=settings.stream_partial_messages,
                # 显式传 disabled，而不是仅在前端隐藏 thinking 事件；这样模型侧也不会启用扩展思考。
                thinking={"type": "adaptive"} if settings.thinking_enabled else {"type": "disabled"},
                resume=conversation.get("sdk_session_id") or None,
                env=self._sdk_env(settings),
            )

            memory = await self.control.get_memory(context.tenant_id, context.user_id)
            prompt = question
            if not conversation.get("sdk_session_id") and memory:
                prompt = (
                    "<core_memory>\n"
                    f"{memory}\n"
                    "</core_memory>\n\n"
                    "<current_user_request>\n"
                    f"{question}\n"
                    "</current_user_request>"
                )

            assistant_texts: list[str] = []
            final_result_text = ""
            last_message: Any | None = None
            known_session_id = conversation.get("sdk_session_id") or None
            async for message in query(prompt=prompt, options=options):
                message_type, subtype = _classify(message)
                if message_type != "stream_event":
                    last_message = message
                await self._handle_message(context, message, message_type, subtype)
                if message_type in {"assistant", "result"}:
                    text = _text_from_message(message)
                    if text and message_type == "assistant" and not _is_partial_assistant(message):
                        assistant_texts.append(text)
                    elif text:
                        final_result_text = text
                session_id = _session_id_of(message)
                # 流式下每个 token 都是一条消息，session 未变化时不能重复写库。
                if session_id and session_id != known_session_id:
                    known_session_id = session_id
                    await self.control.set_sdk_session(context, session_id)
            final_text = final_result_text or (assistant_texts[-1] if assistant_texts else "")
            if not final_text.strip():
                raise ConfigurationError("Agent 未生成最终结果；请查看工具失败事件和运行日志。")
            if final_text.strip():
                await self.control.append_message(context, "assistant", final_text)
            result_message = isinstance(last_message, ResultMessage) if ResultMessage is not None else False
            await self.control.set_run_status(context, "completed", result_mode="success" if result_message else "completed")
            await self.events.publish(context, "run.completed", {"summary": final_text[-20_000:]})
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - 运行失败必须落库并通过 SSE 暴露
            await self.control.set_run_status(context, "failed", result_mode="execution_error", error=str(error))
            await self.events.publish(context, "run.failed", {"error": str(error), "error_type": type(error).__name__})

    async def _handle_message(
        self,
        context: TenantContext,
        message: Any,
        message_type: str,
        subtype: str | None,
    ) -> None:
        if message_type == "stream_event":
            await self._handle_stream_event(context, message)
            return
        event_type = "agent.message"
        if message_type == "system":
            event_type = _system_event_type(subtype, message)
            if event_type is None:
                return
        elif message_type == "assistant":
            # include_partial_messages=True 时 SDK 会下发 stop_reason=None 的流式
            # partial 消息；它们与流式 delta 重复，拼进 narrative 会变成一堆“生长中”
            # 的 agent 消息。只有完成的（stop_reason 非空）才作为权威快照落库广播。
            if _is_partial_assistant(message):
                return
            event_type = "assistant.message"
        elif message_type == "result":
            event_type = "assistant.completed"
        await self.events.publish(context, event_type, _message_event_payload(message, message_type, subtype))

    async def _handle_stream_event(self, context: TenantContext, message: Any) -> None:
        """逐 token 增量默认只广播不落库；开启 persist_stream_deltas 后才写库便于排查。"""
        deltas = _stream_deltas(message)
        if not deltas:
            return
        if get_settings().persist_stream_deltas:
            for event_type, payload in deltas:
                await self.events.publish(context, event_type, payload)
            return
        for event_type, payload in deltas:
            self.events.publish_delta(context, event_type, payload)

    async def _prepare_workspace(self, tenant_id: str) -> Path:
        settings = get_settings()
        workspace = settings.workspace_dir / tenant_id
        workspace.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).resolve().parents[3] / ".claude" / "skills"
        target = workspace / ".claude" / "skills"
        if source.is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, dirs_exist_ok=True)
        return workspace

    @staticmethod
    def _sdk_env(settings) -> dict[str, str]:
        env = {
            "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        }
        if settings.otel_enabled:
            env.update(
                {
                    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
                    "OTEL_TRACES_EXPORTER": "otlp",
                    "OTEL_METRICS_EXPORTER": "otlp",
                    "OTEL_LOGS_EXPORTER": "otlp",
                }
            )
        return env

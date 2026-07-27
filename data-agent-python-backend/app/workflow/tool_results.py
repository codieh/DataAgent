"""面向模型的工具结果契约。

完整结果继续保存在 LangGraph State、SQLite 或结果文件中；ToolMessage 只携带
当前决策所需的真实预览和可追踪引用。这样模型能看到工具实际返回了什么，又不会
把同一份大对象同时塞进 payload、observation 和 ToolMessage。
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any


def build_tool_result(
    observation: dict[str, Any],
    *,
    preview: Any | None = None,
    result_ref: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    """构造统一、可被后续结构化压缩的 ToolMessage 内容。"""
    result = {
        "tool": observation.get("tool"),
        "ok": observation.get("ok", True),
        "summary": observation.get("summary", ""),
    }
    for key in ("error", "retryable", "resultMode"):
        if key in observation:
            result[key] = observation[key]
    if preview is not None:
        result["preview"] = preview
    if result_ref is not None:
        result["resultRef"] = result_ref
    if stats:
        result["stats"] = stats
    result["truncated"] = truncated
    return result


def json_default(value: Any) -> Any:
    """统一处理工具结果中常见的数据库值类型。"""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

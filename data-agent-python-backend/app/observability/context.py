"""跨请求的日志上下文变量。

通过 ``contextvars`` 在异步调用链中透传当前 runId 与 LLM 操作类型，使分散在
各层的日志都能带上统一的追踪字段，方便把一次分析运行的全部日志串起来。
"""

from contextvars import ContextVar


current_run_id: ContextVar[str] = ContextVar("current_run_id", default="-")
current_llm_operation: ContextVar[str] = ContextVar("current_llm_operation", default="text_completion")

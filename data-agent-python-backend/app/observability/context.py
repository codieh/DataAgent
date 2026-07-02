from contextvars import ContextVar


current_run_id: ContextVar[str] = ContextVar("current_run_id", default="-")
current_llm_operation: ContextVar[str] = ContextVar("current_llm_operation", default="text_completion")

"""Agent 工具的运行时元数据。

这些属性不是给模型看的提示词，而是调度器和安全策略可执行的约束。工具新增或
改名时必须在此登记，避免并发、审核和结果持久化继续依赖分散的字符串判断。
"""

from dataclasses import dataclass, field
from typing import Literal


ResultPersistence = Literal["none", "summary", "full"]


@dataclass(frozen=True)
class ToolExecutionMetadata:
    """描述工具是否可并行、是否修改状态以及结果如何持久化。"""

    read_only: bool
    concurrency_safe: bool
    requires_confirmation: bool = False
    result_persistence: ResultPersistence = "summary"
    state_writes: frozenset[str] = field(default_factory=frozenset)


TOOL_EXECUTION_METADATA: dict[str, ToolExecutionMetadata] = {
    "update_analysis_plan": ToolExecutionMetadata(
        read_only=False,
        concurrency_safe=False,
        state_writes=frozenset({"plan"}),
    ),
    "ask_clarification": ToolExecutionMetadata(
        read_only=False,
        concurrency_safe=False,
        state_writes=frozenset({"final_answer", "result_mode"}),
    ),
    "search_schema": ToolExecutionMetadata(
        read_only=True,
        concurrency_safe=True,
        result_persistence="summary",
        state_writes=frozenset(
            {
                "full_schema",
                "schema",
                "selected_tables",
                "schema_reasons",
                "schema_search_count",
            }
        ),
    ),
    "inspect_tables": ToolExecutionMetadata(
        read_only=True,
        concurrency_safe=True,
        result_persistence="summary",
        state_writes=frozenset({"full_schema", "schema", "selected_tables"}),
    ),
    "retrieve_knowledge": ToolExecutionMetadata(
        read_only=True,
        concurrency_safe=True,
        result_persistence="summary",
        state_writes=frozenset({"knowledge"}),
    ),
    "search_history": ToolExecutionMetadata(
        read_only=True,
        concurrency_safe=True,
        result_persistence="summary",
    ),
    "read_conversation_context": ToolExecutionMetadata(
        read_only=True,
        concurrency_safe=True,
        result_persistence="summary",
    ),
    "inspect_query_result": ToolExecutionMetadata(
        read_only=True,
        concurrency_safe=True,
        result_persistence="full",
    ),
    "execute_sql": ToolExecutionMetadata(
        read_only=True,
        concurrency_safe=False,
        requires_confirmation=True,
        result_persistence="full",
        state_writes=frozenset(
            {
                "sql",
                "columns",
                "rows",
                "query_results",
                "analysis_datasets",
                "sql_execution_count",
            }
        ),
    ),
    "analyze_dataframe": ToolExecutionMetadata(
        read_only=False,
        concurrency_safe=False,
        result_persistence="full",
        state_writes=frozenset({"python_analysis", "python_analyses"}),
    ),
    "rewrite_core_memory": ToolExecutionMetadata(
        read_only=False,
        concurrency_safe=False,
        result_persistence="full",
        state_writes=frozenset({"persistent_core_memory"}),
    ),
}


def tool_metadata(name: str) -> ToolExecutionMetadata:
    """返回已登记工具的元数据；未知工具立即失败，避免静默按安全默认值运行。"""

    try:
        return TOOL_EXECUTION_METADATA[name]
    except KeyError as error:
        raise RuntimeError(f"工具缺少运行时元数据: {name}") from error

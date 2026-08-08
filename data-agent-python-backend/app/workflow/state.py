"""分析工作流全局状态定义。

``AnalysisState`` 是 LangGraph 在节点间流转的共享状态（TypedDict，``total=False``
表示所有字段均可选）。``messages`` 字段使用 ``add_messages`` reducer 进行消息合并，
其余字段由节点返回的字典进行覆盖/扩展。状态涵盖：输入、记忆、安全和预算、
Schema/知识、计划、SQL 及其校验/执行、结果、Agent 决策与计数、观察记录等。

约定：节点方法返回“状态增量”dict，LangGraph 负责把增量合并进本状态。
"""

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AnalysisState(TypedDict, total=False):
    """分析工作流的完整状态契约（字段均可选，便于节点增量更新）。"""
    messages: Annotated[list[AnyMessage], add_messages]  # 使用 add_messages reducer 合并对话消息
    run_id: str  # 单次运行的唯一标识，同时作为 LangGraph 的 thread_id
    conversation_id: str  # 会话标识，用于区分不同会话的结果历史
    query: str  # 用户原始查询
    contextualized_query: str  # 结合对话上下文消歧后的查询（更利于检索/SQL 生成）
    memory_context: dict[str, Any]  # 近轮对话、摘要与长期记忆等上下文
    human_review_enabled: bool  # 是否开启 SQL 执行前的人工审核
    human_feedback: dict[str, Any]  # 人工审核反馈（approved/comment 等）
    knowledge: dict[str, list[dict[str, Any]]]  # 检索到的业务知识（documents/evidences）
    schema: dict[str, Any]  # 当前召回的数据库 schema（表与字段）
    schema_reasons: dict[str, str]  # 各表被选中的原因
    plan: dict[str, Any]  # 分析计划（目标、步骤、审核反馈等）
    selected_tables: list[str]  # 计划选定的表
    sql: str  # 当前生成的 SQL
    sql_explanation: str  # SQL 解释
    safety: dict[str, Any]  # SQL 安全校验结论
    columns: list[dict[str, Any]]  # 最近一次查询返回的列元信息
    rows: list[dict[str, Any]]  # 最近一次查询返回的预览行
    retry_count: int  # SQL 修复/重试次数
    sql_error: str | None  # SQL 执行或校验错误
    result_mode: str | None  # 结果模式（success/conversation/blocked_prompt_injection/...）
    analysis: dict[str, Any]  # 最终结构化分析报告
    error: str | None  # 顶层终态错误；单次 SQL 失败应写入 sql_error/observations
    security: dict[str, Any]  # 输入安全校验结论
    agent_decision: dict[str, Any]  # Agent 本轮决策（action/arguments/reasonSummary）
    agent_iterations: int  # Agent 已执行的决策轮数
    schema_search_count: int  # schema 检索累计次数（预算控制）
    sql_execution_count: int  # SQL 执行累计次数（预算控制）
    # 工具可并行完成；每个工具只返回本次增量，由 reducer 合并为完整观察轨迹。
    observations: Annotated[list[dict[str, Any]], operator.add]
    final_answer: str  # Agent 结束时的结论文本
    full_schema: dict[str, Any]  # 完整 schema（区别于裁剪后的 schema）
    query_results: list[dict[str, Any]]  # 所有已执行查询的结果集清单
    python_analyses: list[dict[str, Any]]  # Python 分析产出（供结果合并）
    analysis_datasets: list[dict[str, Any]]  # 持久化的分析数据集元信息
    context_compaction: dict[str, Any]  # 活动上下文压缩边界、结构化摘要与 Token 统计

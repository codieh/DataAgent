"""工作流结构化输出模型。

本模块用 Pydantic 模型约束各工作流步骤的 LLM 结构化输出，便于
``LlmClient.complete_model`` 反序列化与校验。所有模型均继承自 ``WorkflowOutput``，
统一配置 ``extra="ignore"``（忽略多余字段）与 ``populate_by_name=True``（支持别名填充）。

字段命名采用 Python 风格，对外 JSON 通过 ``alias`` 暴露驼峰命名（如 ``successCriteria``）。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowOutput(BaseModel):
    """所有工作流输出模型的基类：忽略未知字段并允许按别名填充。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class SchemaRecallOutput(WorkflowOutput):
    """Schema 召回结果：从真实 schema 中选出的候选表及其选择原因。"""

    selected_tables: list[str] = Field(default_factory=list)
    reasons: dict[str, str] = Field(default_factory=dict)


class PlanStepOutput(WorkflowOutput):
    """分析计划的单个步骤。"""

    id: str
    title: str
    objective: str
    index: int | None = None
    status: str | None = None


class PlanOutput(WorkflowOutput):
    """分析计划：目标、成功标准、所选表与步骤序列。"""

    goal: str = ""
    success_criteria: list[str] = Field(default_factory=list, alias="successCriteria")
    selected_tables: list[str] = Field(default_factory=list)
    steps: list[PlanStepOutput] = Field(default_factory=list)


class SqlOutput(WorkflowOutput):
    """SQL 生成结果：只读 SELECT 语句及其解释。"""

    sql: str
    explanation: str = ""


class FindingOutput(WorkflowOutput):
    """分析发现：一条业务结论，可关联若干指标与结果集。"""

    id: str
    title: str
    description: str
    severity: str = "info"
    metric_ids: list[str] = Field(default_factory=list, alias="metricIds")
    source_result_set_ids: list[str] = Field(default_factory=list, alias="sourceResultSetIds")


class MetricOutput(WorkflowOutput):
    """分析指标：一个带格式化展示的数值指标。"""

    id: str
    label: str
    value: Any = None
    formatted_value: str = Field(default="", alias="formattedValue")
    unit: str = ""
    description: str = ""
    source_result_set_id: str = Field(default="", alias="sourceResultSetId")


class ChartOutput(WorkflowOutput):
    """图表配置：图表类型、字段映射与可选内联数据。"""

    id: str
    type: str
    title: str
    result_set_id: str = Field(default="", alias="resultSetId")
    x_field: str = Field(alias="xField")
    y_fields: list[str] = Field(default_factory=list, alias="yFields")
    series_field: str | None = Field(default=None, alias="seriesField")
    options: dict[str, Any] = Field(default_factory=dict)
    data: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisStructureOutput(WorkflowOutput):
    """最终报告的结构化部分；可见总结由独立流式请求生成。"""

    title: str = "分析结果"
    findings: list[FindingOutput] = Field(default_factory=list)
    metrics: list[MetricOutput] = Field(default_factory=list)
    charts: list[ChartOutput] = Field(default_factory=list)


class MemoryOperationOutput(WorkflowOutput):
    """单条长期记忆操作：新增/更新（upsert）或删除（delete）。"""

    action: Literal["upsert", "delete"]
    key: str
    kind: Literal["preference", "business_rule", "correction", "user_profile"]
    content: str = ""
    confidence: float = 0.0


class MemoryExtractionOutput(WorkflowOutput):
    """会话长期记忆提取结果：一组记忆操作。"""

    operations: list[MemoryOperationOutput] = Field(default_factory=list)


class CoreMemoryRewriteOutput(WorkflowOutput):
    """核心记忆改写结果：改写后的完整记忆内容与是否发生变化。"""

    content: str = ""
    changed: bool = False
    summary: str = ""


class ConversationSummaryOutput(WorkflowOutput):
    """会话摘要结果。"""

    summary: str


class PythonCodeOutput(WorkflowOutput):
    """受控 Python 分析代码生成结果：脚本与解释。"""

    code: str
    explanation: str = ""

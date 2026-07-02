from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class IntentOutput(WorkflowOutput):
    classification: str = "DATA_ANALYSIS"
    contextualized_query: str = ""
    execution_path: str = "simple"


class SchemaRecallOutput(WorkflowOutput):
    selected_tables: list[str] = Field(default_factory=list)
    reasons: dict[str, str] = Field(default_factory=dict)


class PlanStepOutput(WorkflowOutput):
    id: str
    title: str
    objective: str
    index: int | None = None
    status: str | None = None


class PlanOutput(WorkflowOutput):
    goal: str = ""
    success_criteria: list[str] = Field(default_factory=list, alias="successCriteria")
    selected_tables: list[str] = Field(default_factory=list)
    steps: list[PlanStepOutput] = Field(default_factory=list)


class SqlOutput(WorkflowOutput):
    sql: str
    explanation: str = ""


class FindingOutput(WorkflowOutput):
    id: str
    title: str
    description: str
    severity: str = "info"
    metric_ids: list[str] = Field(default_factory=list, alias="metricIds")
    source_result_set_ids: list[str] = Field(default_factory=list, alias="sourceResultSetIds")


class MetricOutput(WorkflowOutput):
    id: str
    label: str
    value: Any = None
    formatted_value: str = Field(default="", alias="formattedValue")
    unit: str = ""
    description: str = ""
    source_result_set_id: str = Field(default="", alias="sourceResultSetId")


class ChartOutput(WorkflowOutput):
    id: str
    type: str
    title: str
    result_set_id: str = Field(default="", alias="resultSetId")
    x_field: str = Field(alias="xField")
    y_fields: list[str] = Field(default_factory=list, alias="yFields")
    series_field: str | None = Field(default=None, alias="seriesField")
    options: dict[str, Any] = Field(default_factory=dict)


class AnalysisOutput(WorkflowOutput):
    title: str = "分析结果"
    summary: str = ""
    findings: list[FindingOutput] = Field(default_factory=list)
    metrics: list[MetricOutput] = Field(default_factory=list)
    charts: list[ChartOutput] = Field(default_factory=list)

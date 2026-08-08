"""跨层使用的领域数据结构。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    user_id: str
    conversation_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class Verification:
    status: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Goal:
    goal: str
    metrics: list[dict[str, Any]] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    filters: list[dict[str, Any]] = field(default_factory=list)
    time_range: dict[str, Any] = field(default_factory=dict)
    ranking: dict[str, Any] = field(default_factory=dict)
    limit: int | None = None
    expected_tables: list[str] = field(default_factory=list)
    expected_output: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "metrics": self.metrics,
            "dimensions": self.dimensions,
            "filters": self.filters,
            "time_range": self.time_range,
            "ranking": self.ranking,
            "limit": self.limit,
            "expected_tables": self.expected_tables,
            "expected_output": self.expected_output,
        }

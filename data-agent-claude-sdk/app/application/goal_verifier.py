"""分析目标和 SQL/结果之间的确定性校验。"""

import re
from typing import Any

from app.domain.models import Goal, QueryResult, Verification


class ResultVerifier:
    """先做可解释的字符串/结构检查，再把不确定语义交给后续模型处理。"""

    def verify(self, goal: Goal, sql: str, result: QueryResult) -> Verification:
        sql_lower = sql.lower()
        checks: list[dict[str, Any]] = []
        mismatches: list[str] = []

        for table in goal.expected_tables:
            passed = re.search(rf"\b{re.escape(table.lower())}\b", sql_lower) is not None
            checks.append({"name": f"table:{table}", "passed": passed})
            if not passed:
                mismatches.append(f"SQL 未使用目标表 {table}")

        for metric in goal.metrics:
            field = str(metric.get("field") or metric.get("name") or "").strip().lower()
            if not field:
                continue
            passed = field in sql_lower
            checks.append({"name": f"metric:{field}", "passed": passed})
            if not passed:
                mismatches.append(f"SQL 未体现指标字段 {field}")

        for dimension in goal.dimensions:
            field = str(dimension).lower()
            passed = field in sql_lower
            checks.append({"name": f"dimension:{field}", "passed": passed})
            if not passed:
                mismatches.append(f"SQL 未体现维度 {dimension}")

        for condition in goal.filters:
            field = str(condition.get("field", "")).lower()
            value = str(condition.get("value", "")).lower()
            field_ok = not field or field in sql_lower
            value_ok = not value or value in sql_lower
            passed = field_ok and value_ok
            checks.append({"name": f"filter:{field}", "passed": passed})
            if not passed:
                mismatches.append(f"SQL 未完整体现过滤条件 {field}={value}")

        if goal.limit is not None:
            limit_match = re.search(r"\blimit\s+(\d+)", sql_lower)
            passed = bool(limit_match and int(limit_match.group(1)) <= goal.limit)
            checks.append({"name": "requested_limit", "passed": passed})
            if not passed:
                mismatches.append(f"SQL 未满足 Top {goal.limit} 的限制")

        if not result.columns:
            mismatches.append("查询没有返回字段")
        checks.append({"name": "result_columns", "passed": bool(result.columns)})
        status = "passed" if not mismatches else "needs_revision"
        return Verification(status=status, checks=checks, mismatches=mismatches)

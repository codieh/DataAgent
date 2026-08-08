from app.application.goal_verifier import ResultVerifier
from app.domain.models import Goal, QueryResult


def test_result_verifier_accepts_goal_aligned_sql():
    goal = Goal(
        goal="统计已完成订单金额",
        metrics=[{"field": "total_amount"}],
        filters=[{"field": "status", "value": "completed"}],
        expected_tables=["orders"],
    )
    result = ResultVerifier().verify(
        goal,
        "SELECT SUM(total_amount) AS total_amount FROM orders WHERE status = 'completed'",
        QueryResult(["total_amount"], [{"total_amount": 100}], 1, False),
    )

    assert result.status == "passed"
    assert result.mismatches == []


def test_result_verifier_reports_missing_filter():
    goal = Goal(
        goal="统计已完成订单金额",
        metrics=[{"field": "total_amount"}],
        filters=[{"field": "status", "value": "completed"}],
        expected_tables=["orders"],
    )
    result = ResultVerifier().verify(
        goal,
        "SELECT SUM(total_amount) FROM orders",
        QueryResult(["total_amount"], [{"total_amount": 100}], 1, False),
    )

    assert result.status == "needs_revision"
    assert any("completed" in mismatch for mismatch in result.mismatches)

import json
from datetime import date, datetime, time
from decimal import Decimal

from app.workflow.nodes.analysis import _json_default


def test_sql_result_values_are_serialized_for_result_prompt() -> None:
    payload = {
        "order_date": date(2026, 7, 1),
        "created_at": datetime(2026, 7, 1, 12, 30, 45),
        "cutoff": time(18, 0),
        "amount": Decimal("1234.50"),
        "raw": b"ok",
    }

    encoded = json.loads(json.dumps(payload, default=_json_default))

    assert encoded == {
        "order_date": "2026-07-01",
        "created_at": "2026-07-01T12:30:45",
        "cutoff": "18:00:00",
        "amount": "1234.50",
        "raw": "ok",
    }

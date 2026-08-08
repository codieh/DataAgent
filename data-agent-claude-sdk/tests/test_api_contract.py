import json

from app.api.routes import _event_view, _sse


def test_run_event_snapshot_uses_same_envelope_as_sse():
    event = {
        "event_id": "evt-1",
        "seq": 3,
        "type": "sql.executed",
        "created_at": "2026-08-06 09:30:00",
        "payload": {"result_ref": "result-1", "row_count": 2},
    }

    assert _event_view(event) == {
        "event_id": "evt-1",
        "seq": 3,
        "type": "sql.executed",
        "timestamp": "2026-08-06 09:30:00",
        "data": {"result_ref": "result-1", "row_count": 2},
        "ephemeral": False,
    }


def test_durable_sse_frame_carries_resumable_id():
    frame = _sse({"event_id": "evt-1", "seq": 7, "type": "sql.executed", "payload": {"row_count": 2}})

    assert "id: 7\n" in frame
    body = json.loads(frame.split("data: ", 1)[1])
    assert body["ephemeral"] is False
    assert body["seq"] == 7


def test_delta_sse_frame_has_no_id_so_it_never_moves_the_resume_cursor():
    frame = _sse({
        "event_id": None,
        "seq": None,
        "type": "assistant.message.delta",
        "payload": {"kind": "text", "delta": "订单"},
        "ephemeral": True,
    })

    assert "\nid:" not in frame
    body = json.loads(frame.split("data: ", 1)[1])
    assert body["ephemeral"] is True
    assert body["data"] == {"kind": "text", "delta": "订单"}

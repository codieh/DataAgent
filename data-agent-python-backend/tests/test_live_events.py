"""进程内运行事件 Broker 测试。"""

import pytest

from app.application.live_events import RunLiveEventBroker


@pytest.mark.asyncio
async def test_broker_delivers_transient_event_without_polling() -> None:
    broker = RunLiveEventBroker()
    async with broker.subscribe("run_1") as subscription:
        broker.publish_transient("run_1", {"type": "final_answer.delta", "data": {"delta": "增长"}})

        event = await subscription.queue.get()

    assert event["kind"] == "transient"
    assert event["eventId"].startswith("live-run_1-")
    assert event["seq"] is None
    assert event["timestamp"]
    assert event["data"]["delta"] == "增长"


@pytest.mark.asyncio
async def test_broker_reports_slow_consumer_instead_of_dropping_silently() -> None:
    broker = RunLiveEventBroker(queue_size=1)
    async with broker.subscribe("run_1") as subscription:
        broker.publish_transient("run_1", {"type": "first"})
        broker.publish_transient("run_1", {"type": "second"})

        event = await subscription.queue.get()

    assert subscription.overflowed is True
    assert event == {"kind": "overflow"}

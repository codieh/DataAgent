"""持久化事件与进程内 SSE 广播。

事件分两类：

* **持久化事件**（``publish``）：写入 ``run_events`` 并广播，带单调递增的 ``seq``，
  客户端断线后可用 ``after_seq`` 补齐，是运行历史的唯一真相。
* **增量事件**（``publish_delta``）：只广播不落库，用于逐 token 的流式输出。
  丢失只会影响打字机效果，每轮结束的持久化快照会补齐完整内容，因此在队列
  压力下宁可丢弃增量，也不能把持久化事件挤掉或触发整条流重连。
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.domain.models import TenantContext
from app.infrastructure.persistence.database import ControlDatabase

QUEUE_MAXSIZE = 1000
# 增量事件只允许占用队列的前半段，给持久化事件留出余量。
DELTA_HIGH_WATERMARK = QUEUE_MAXSIZE // 2


class EventBroker:
    def __init__(self, database: ControlDatabase):
        self.database = database
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers.setdefault(run_id, set()).add(queue)
        try:
            yield queue
        finally:
            subscribers = self._subscribers.get(run_id)
            if subscribers:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(run_id, None)

    async def publish(self, context: TenantContext, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = await self.database.append_event(context, event_type, payload)
        self._fanout(context.run_id, event)
        return event

    def publish_delta(self, context: TenantContext, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """广播一条不落库的流式增量事件。

        同步方法：只做 ``put_nowait``，不触发任何 IO，避免逐 token 的 await 开销。
        """
        event = {
            "event_id": None,
            "seq": None,
            "type": event_type,
            "payload": payload,
            "ephemeral": True,
        }
        self._fanout(context.run_id, event, droppable=True)
        return event

    def _fanout(self, run_id: str, event: dict[str, Any], droppable: bool = False) -> None:
        for queue in list(self._subscribers.get(run_id, ())):
            if droppable and queue.qsize() >= DELTA_HIGH_WATERMARK:
                # 消费端跟不上打字机速度：丢弃增量，最终快照仍会送达。
                continue
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                if droppable:
                    continue
                # 慢消费者必须通过 SSE 重连从数据库补事件，不能静默丢持久化事件。
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "stream.overflow", "run_id": run_id})

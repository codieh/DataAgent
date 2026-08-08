"""运行事件的进程内实时发布订阅通道。

持久事件先写 SQLite，再广播到在线 SSE；Token 增量只广播、不落库。SQLite 负责审计
与断线补偿，Broker 只负责低延迟通知，避免 SSE 通过高频轮询充当消息队列。
"""

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, AsyncIterator
from uuid import uuid4


logger = logging.getLogger(__name__)
_OVERFLOW = {"kind": "overflow"}


@dataclass(eq=False)
class LiveSubscription:
    """单个 SSE 客户端的有界事件队列。"""

    queue: asyncio.Queue[dict[str, Any]]
    overflowed: bool = False


class RunLiveEventBroker:
    """按 run_id 隔离订阅者，并显式处理慢消费者。"""

    def __init__(self, queue_size: int = 512) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self.queue_size = queue_size
        self._subscribers: dict[str, set[LiveSubscription]] = defaultdict(set)

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[LiveSubscription]:
        subscription = LiveSubscription(asyncio.Queue(maxsize=self.queue_size))
        self._subscribers[run_id].add(subscription)
        try:
            yield subscription
        finally:
            subscribers = self._subscribers.get(run_id)
            if subscribers is not None:
                subscribers.discard(subscription)
                if not subscribers:
                    self._subscribers.pop(run_id, None)

    def publish_persistent(self, event: Any) -> None:
        """广播已经成功落库的事件，保留数据库 seq 供 SSE 去重和续传。"""
        self._publish(
            str(event.run_id),
            {
                "kind": "persistent",
                "eventId": str(event.id),
                "conversationId": str(event.conversation_id),
                "runId": str(event.run_id),
                "seq": int(event.seq),
                "type": str(event.type),
                "stage": event.stage,
                "timestamp": event.created_at.isoformat(),
                "data": event.data,
            },
        )

    def publish_transient(self, run_id: str, event: dict[str, Any]) -> None:
        """广播不持久化事件；它有唯一身份，但不占用持久事件续传游标。"""
        self._publish(
            run_id,
            {
                "kind": "transient",
                **event,
                "eventId": f"live-{run_id}-{uuid4().hex}",
                "seq": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _publish(self, run_id: str, event: dict[str, Any]) -> None:
        for subscription in tuple(self._subscribers.get(run_id, ())):
            if subscription.overflowed:
                continue
            try:
                subscription.queue.put_nowait(event)
            except asyncio.QueueFull:
                # 明确终止慢订阅者；持久事件可通过 seq 重连，最终文本可由 Run 快照恢复。
                subscription.overflowed = True
                while not subscription.queue.empty():
                    subscription.queue.get_nowait()
                subscription.queue.put_nowait(_OVERFLOW)
                logger.warning(
                    "live event subscriber overflowed: runId=%s queueSize=%d",
                    run_id,
                    self.queue_size,
                )


run_live_event_broker = RunLiveEventBroker()

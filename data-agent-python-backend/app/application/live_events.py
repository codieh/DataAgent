"""运行期间的临时实时事件通道。

Token 增量只服务于当前在线的 SSE 客户端，不写入 ``run_events``。最终分析结果仍由
执行器持久化；客户端断线后通过 Run 快照恢复，不依赖重放每个 Token。
"""

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


class RunLiveEventBroker:
    """按 run_id 隔离订阅者的进程内发布订阅器。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    @asynccontextmanager
    async def subscribe(self, run_id: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[run_id].add(queue)
        try:
            yield queue
        finally:
            subscribers = self._subscribers.get(run_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(run_id, None)

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        """向当前在线订阅者广播；没有订阅者时无需保留临时 Token。"""
        for queue in tuple(self._subscribers.get(run_id, ())):
            queue.put_nowait(event)


run_live_event_broker = RunLiveEventBroker()

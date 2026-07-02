import asyncio
from collections.abc import Coroutine
from typing import Any

from app.domain.enums import TERMINAL_RUN_STATUSES


TERMINAL_STATUSES = {status.value for status in TERMINAL_RUN_STATUSES}


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, run_id: str, coroutine: Coroutine[Any, Any, None]) -> None:
        previous = self._tasks.get(run_id)
        if previous and not previous.done():
            coroutine.close()
            return
        task = asyncio.create_task(coroutine, name=f"analysis-run-{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(run_id, None))

    def cancel(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


task_registry = TaskRegistry()

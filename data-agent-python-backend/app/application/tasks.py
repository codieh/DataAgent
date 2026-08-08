"""分析运行后台任务的注册与生命周期管理。

系统中每次分析运行都由 asyncio 后台任务（asyncio.Task）异步驱动。本模块提供
一个进程级注册表 TaskRegistry，以 run_id 为键管理这些任务，保证同一运行最多
只有一份活跃任务，并在需要时支持取消、等待与整体关闭。

TERMINAL_STATUSES 为运行终态集合的便捷快照，供控制/视图层判断运行是否已结束。
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from app.domain.enums import TERMINAL_RUN_STATUSES


# 运行终态集合（字符串值形式），便于与数据库中的 status 字段直接比较。
TERMINAL_STATUSES = {status.value for status in TERMINAL_RUN_STATUSES}


class TaskRegistry:
    """以 run_id 为键的分析运行任务注册表。"""

    def __init__(self) -> None:
        # run_id -> asyncio.Task 的映射，集中持有所有进行中的运行任务。
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, run_id: str, coroutine: Coroutine[Any, Any, None]) -> None:
        """启动（或复用）某运行的后台任务。

        若同一 run_id 已有未完成的任务，则放弃新协程（close）以避免重复执行；
        否则创建任务并在其完成时自动从注册表移除。
        """
        previous = self._tasks.get(run_id)
        if previous and not previous.done():
            # 已存在活跃任务，丢弃新请求对应的协程。
            coroutine.close()
            return
        task = asyncio.create_task(coroutine, name=f"analysis-run-{run_id}")
        self._tasks[run_id] = task
        # 任务结束时自我清理，防止注册表无限增长。
        task.add_done_callback(lambda _task: self._tasks.pop(run_id, None))

    def cancel(self, run_id: str) -> None:
        """取消某运行的后台任务（若仍在运行）。"""
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()

    async def cancel_and_wait(self, run_id: str) -> None:
        """取消某运行的后台任务并等待其真正结束。"""
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            # 等待取消完成；return_exceptions 避免取消异常向上传播。
            await asyncio.gather(task, return_exceptions=True)

    async def wait_for_completion(self, run_id: str) -> None:
        """等待指定 Run 的旧后台任务彻底退出，避免失败后立即重试的启动竞态。"""
        task = self._tasks.get(run_id)
        if task and not task.done():
            await asyncio.gather(task, return_exceptions=True)

    async def shutdown(self) -> None:
        """关闭注册表：取消全部进行中的任务并等待全部结束，最后清空映射。"""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


# 进程级单例注册表，供命令/控制服务共享同一份任务视图。
task_registry = TaskRegistry()

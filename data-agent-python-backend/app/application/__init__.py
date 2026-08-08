"""应用层用例（Application Use Cases）。

该包承载系统的「用例编排」职责，处于接口层（API/调度）与领域/基础设施层之间：
对外暴露面向业务场景的服务类与函数，对内协调领域对象、运行时（GraphRuntime）
与持久化仓库（Repository）完成一次完整的分析任务生命周期。

主要组成：
- conversations: 会话详情查询服务。
- recovery: 应用重启后对中断任务的补偿处理。
- run_control: 运行任务的取消等控制操作。
- run_views: 运行结果、产物与审核视图的组装。
- run_commands: 创建运行、重试、人工审核决策等写操作命令。
- tasks: 运行后台任务（asyncio.Task）的注册表与生命周期管理。
- executor: 驱动 LangGraph 执行并把流式更新落库为产物/事件的核心执行器。

本模块仅做统一出口（re-export），便于上层按需导入。
"""

from app.application.conversations import ConversationService
from app.application.recovery import recover_interrupted_runs
from app.application.run_control import WorkflowControlService
from app.application.run_views import RunViewService
from app.application.tasks import TERMINAL_STATUSES, task_registry

__all__ = [
    "ConversationService",
    "RunViewService",
    "TERMINAL_STATUSES",
    "WorkflowControlService",
    "recover_interrupted_runs",
    "task_registry",
]


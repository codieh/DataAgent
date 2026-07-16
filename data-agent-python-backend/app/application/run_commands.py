"""运行相关的写操作命令（Command）。

与应用层「用例」对应的命令侧实现，负责产生副作用的操作：
- RunCommandService：创建分析运行、对已有运行发起重试。
- ReviewCommandService：处理人工审核决策（批准/驳回），并驱动图恢复或重规划。

这些命令在创建运行后通过 task_registry 派发后台 asyncio 任务驱动执行器，
因此「创建」与「真正执行」是异步解耦的。
"""

from app.application.executor import workflow
from app.application.live_events import run_live_event_broker
from app.application.tasks import task_registry
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.models import utc_now
from app.infrastructure.persistence.repository import Repository


class RunCommandService:
    """分析运行的创建与重试命令。"""

    def __init__(self, repository: Repository):
        self.repository = repository

    async def create(
        self,
        *,
        conversation_id: str,
        query: str,
        human_review_enabled: bool,
        idempotency_key: str | None,
        agent_id: str | None = None,
        datasource_id: str | None = None,
        retry_of_run_id: str | None = None,
    ):
        """创建一个新的分析运行并立即派发后台执行任务。

        参数:
            conversation_id: 所属会话 ID（必须存在，否则抛 ResourceNotFoundError）。
            query: 用户原始问题。
            human_review_enabled: 是否启用人工审核（影响后续是否中断等待确认）。
            idempotency_key: 幂等键；若已存在同键运行则直接返回原运行，避免重复创建。
            agent_id / datasource_id: 可选，用于绑定/更新会话关联的智能体与数据源。
            retry_of_run_id: 可选，标记本次运行是某次运行的重试。
        返回:
            已创建（或命中幂等的既有）运行记录。
        副作用:
            写入运行、用户消息，必要时更新会话标题，并启动后台执行任务。
        """
        conversation = await self.repository.get_conversation(conversation_id)
        if not conversation:
            raise ResourceNotFoundError("conversation", conversation_id)
        # 幂等保护：相同幂等键直接复用既有运行。
        if idempotency_key:
            existing = await self.repository.find_run_by_idempotency_key(idempotency_key)
            if existing:
                return existing
        # 若本次请求携带智能体/数据源，则同步更新到会话维度。
        if agent_id or datasource_id:
            await self.repository.update_conversation(
                conversation,
                agent_id=agent_id,
                datasource_id=datasource_id,
            )
        run = await self.repository.create_run(
            conversation=conversation,
            question=query.strip(),
            human_review_enabled=human_review_enabled,
            idempotency_key=idempotency_key,
            retry_of_run_id=retry_of_run_id,
        )
        # 将原始问题作为用户消息写入会话，保证对话流完整。
        await self.repository.add_message(
            conversation_id=conversation_id,
            run_id=run.id,
            role="user",
            content=run.question,
        )
        # 会话标题仍为默认值时，用首条问题前 60 字作为会话标题。
        if conversation.title == "新建分析":
            await self.repository.update_conversation(conversation, title=run.question[:60])
        # 派发后台任务驱动执行器；该调用立即返回，执行异步进行。
        task_registry.start(run.id, workflow.run(run.id))
        return run

    async def retry(self, run_id: str):
        """基于已有运行重新发起一次运行（沿用原问题/审核配置，并标记为重试）。"""
        original = await self.repository.get_run(run_id)
        if not original:
            raise ResourceNotFoundError("run", run_id)
        # 重试不携带幂等键（不应复用原运行），并记录 retry_of_run_id 溯源。
        return await self.create(
            conversation_id=original.conversation_id,
            query=original.question,
            human_review_enabled=original.human_review_enabled,
            idempotency_key=None,
            retry_of_run_id=original.id,
        )


class ReviewCommandService:
    """人工审核决策命令。"""

    def __init__(self, repository: Repository):
        self.repository = repository

    async def decide(self, review_id: str, *, approved: bool, comment: str | None):
        """处理一次审核决策：批准则恢复执行，驳回则按意见重规划。

        参数:
            review_id: 审核记录 ID。
            approved: 是否批准。
            comment: 审核意见（驳回时通常非空）。
        返回:
            更新后的审核记录。若审核已处理过（非 waiting）则原样返回，幂等。
        副作用:
            更新审核记录与运行状态，并启动对应的后台恢复/重规划任务。
        """
        review = await self.repository.get_review(review_id)
        if not review:
            raise ResourceNotFoundError("review", review_id)
        # 已处理过的审核直接返回，避免重复驱动。
        if review.status != "waiting":
            return review
        review.status = "approved" if approved else "rejected"
        review.review_comment = comment
        review.reviewed_at = utc_now()
        await self.repository.save_review(review)
        run = await self.repository.get_run(review.run_id)
        if not run:
            raise ResourceNotFoundError("run", review.run_id)
        # 审核落定后把运行复位为运行中，等待图恢复。
        run.status = "running"
        run.result_mode = None
        await self.repository.save_run(run)
        event = await self.repository.add_event(
            run_id=run.id,
            conversation_id=run.conversation_id,
            event_type="stage.completed",
            stage="human_feedback",
            data={
                "status": review.status,
                "comment": comment or "",
                "message": "审核通过，继续执行" if approved else "已根据审核意见重新规划",
            },
        )
        run_live_event_broker.publish_persistent(event)
        # 根据决策方向驱动不同的图恢复入口。
        if approved:
            task_registry.start(run.id, workflow.resume_after_review(run.id))
        else:
            task_registry.start(run.id, workflow.replan_after_rejection(run.id, comment or ""))
        return review

from app.application.executor import workflow
from app.application.tasks import task_registry
from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.models import utc_now
from app.infrastructure.persistence.repository import Repository


class RunCommandService:
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
        conversation = await self.repository.get_conversation(conversation_id)
        if not conversation:
            raise ResourceNotFoundError("conversation", conversation_id)
        if idempotency_key:
            existing = await self.repository.find_run_by_idempotency_key(idempotency_key)
            if existing:
                return existing
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
        await self.repository.add_message(
            conversation_id=conversation_id,
            run_id=run.id,
            role="user",
            content=run.question,
        )
        if conversation.title == "新建分析":
            await self.repository.update_conversation(conversation, title=run.question[:60])
        task_registry.start(run.id, workflow.run(run.id))
        return run

    async def retry(self, run_id: str):
        original = await self.repository.get_run(run_id)
        if not original:
            raise ResourceNotFoundError("run", run_id)
        return await self.create(
            conversation_id=original.conversation_id,
            query=original.question,
            human_review_enabled=original.human_review_enabled,
            idempotency_key=None,
            retry_of_run_id=original.id,
        )


class ReviewCommandService:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def decide(self, review_id: str, *, approved: bool, comment: str | None):
        review = await self.repository.get_review(review_id)
        if not review:
            raise ResourceNotFoundError("review", review_id)
        if review.status != "waiting":
            return review
        review.status = "approved" if approved else "rejected"
        review.review_comment = comment
        review.reviewed_at = utc_now()
        await self.repository.save_review(review)
        run = await self.repository.get_run(review.run_id)
        if not run:
            raise ResourceNotFoundError("run", review.run_id)
        run.status = "running"
        run.result_mode = None
        await self.repository.save_run(run)
        await self.repository.add_event(
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
        if approved:
            task_registry.start(run.id, workflow.resume_after_review(run.id))
        else:
            task_registry.start(run.id, workflow.replan_after_rejection(run.id, comment or ""))
        return review


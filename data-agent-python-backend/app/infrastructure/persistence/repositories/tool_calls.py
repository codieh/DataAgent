"""工具调用仓储（Tool call repository）。

记录 Agent 在运行中发起的工具（function call）调用（``ToolCallModel``），覆盖
「开始 → 完成/失败」的生命周期，并计算耗时。

``start_tool_call`` 对同 ``(run_id, tool_call_id)`` 幂等：已存在则直接返回旧记录，
避免重试时重复创建；``sequence`` 在同运行内按最大序号 +1 递增，保证调用顺序稳定。
"""

from sqlalchemy import func, select

from app.infrastructure.persistence.models import ToolCallModel, elapsed_ms, utc_now
from app.infrastructure.persistence.repositories.base import RepositoryBase, new_id


class ToolCallRepository(RepositoryBase):
    """工具调用聚合的仓储实现。"""

    async def start_tool_call(
        self,
        *,
        conversation_id: str,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict,
    ) -> ToolCallModel:
        """开始一次工具调用；若同 ``(run_id, tool_call_id)`` 已存在则幂等返回。

        仅在新建时分配 ``sequence``（取该运行当前最大序号 +1），并记录入参与起始时间。
        """
        existing = await self.session.scalar(
            select(ToolCallModel).where(
                ToolCallModel.run_id == run_id,
                ToolCallModel.tool_call_id == tool_call_id,
            )
        )
        if existing is not None:
            return existing
        sequence = int(
            await self.session.scalar(
                select(func.coalesce(func.max(ToolCallModel.sequence), 0)).where(ToolCallModel.run_id == run_id)
            )
            or 0
        ) + 1
        call = ToolCallModel(
            id=new_id("tool"),
            conversation_id=conversation_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            sequence=sequence,
            tool_name=tool_name,
            arguments_json=arguments,
        )
        self.session.add(call)
        await self.session.commit()
        await self.session.refresh(call)
        return call

    async def complete_tool_call(self, *, run_id: str, tool_call_id: str, result) -> ToolCallModel | None:
        """标记工具调用成功：写入结果、状态与耗时；找不到记录时返回 None。"""
        call = await self.session.scalar(
            select(ToolCallModel).where(
                ToolCallModel.run_id == run_id,
                ToolCallModel.tool_call_id == tool_call_id,
            )
        )
        if call is None:
            return None
        call.result_json = result
        call.status = "success"
        call.completed_at = utc_now()
        call.duration_ms = elapsed_ms(call.started_at, call.completed_at)
        await self.session.commit()
        await self.session.refresh(call)
        return call

    async def fail_tool_call(self, *, run_id: str, tool_call_id: str, error: dict) -> ToolCallModel | None:
        """标记工具调用失败：写入错误信息、状态与耗时；找不到记录时返回 None。"""
        call = await self.session.scalar(
            select(ToolCallModel).where(
                ToolCallModel.run_id == run_id,
                ToolCallModel.tool_call_id == tool_call_id,
            )
        )
        if call is None:
            return None
        call.error_json = error
        call.status = "failed"
        call.completed_at = utc_now()
        call.duration_ms = elapsed_ms(call.started_at, call.completed_at)
        await self.session.commit()
        await self.session.refresh(call)
        return call

    async def list_tool_calls(self, run_id: str) -> list[ToolCallModel]:
        """列出某运行下的全部工具调用，按 ``sequence`` 升序（即调用发生顺序）。"""
        statement = (
            select(ToolCallModel)
            .where(ToolCallModel.run_id == run_id)
            .order_by(ToolCallModel.sequence.asc())
        )
        return list((await self.session.scalars(statement)).all())

"""会话相关的应用用例。

提供会话层级信息的只读查询，目前主要服务于「会话详情」场景：根据会话 ID
聚合会话本身、其消息列表以及运行（Run）列表，封装为视图对象返回。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ResourceNotFoundError
from app.domain.views import ConversationView
from app.infrastructure.persistence.repository import Repository


class ConversationService:
    """会话查询服务：围绕会话维度提供聚合只读视图。"""

    def __init__(self, session: AsyncSession):
        # 复用 Repository 完成所有持久化读取，服务本身不持有业务状态。
        self.repository = Repository(session)

    async def detail(self, conversation_id: str) -> ConversationView:
        """获取单个会话的完整视图。

        参数:
            conversation_id: 目标会话 ID。
        返回:
            ConversationView，包含会话本体、消息列表与运行列表。
        副作用:
            会话不存在时抛出 ResourceNotFoundError。
        """
        conversation = await self.repository.get_conversation(conversation_id)
        if not conversation:
            raise ResourceNotFoundError("conversation", conversation_id)
        return ConversationView(
            conversation=conversation,
            # 并行抓取该会话下的全部消息与运行记录，组装为统一视图。
            messages=await self.repository.list_messages(conversation_id),
            runs=await self.repository.list_runs(conversation_id),
        )


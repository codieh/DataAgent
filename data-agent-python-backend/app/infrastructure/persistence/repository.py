"""统一仓储门面（Repository facade）。

本模块定义 ``Repository``：通过多重继承把各聚合专属仓储（对话、运行、产物、
审核、事件、工具调用）组合为一个类，从而在单次数据库会话（``AsyncSession``）
中即可调用跨聚合的读写方法，共享同一事务边界，便于统一提交/回滚。

调用方通常依赖注入 ``Repository`` 而非各个子仓储，降低耦合。
"""

from app.infrastructure.persistence.repositories.artifacts import ArtifactRepository
from app.infrastructure.persistence.repositories.conversations import ConversationRepository
from app.infrastructure.persistence.repositories.events import EventRepository
from app.infrastructure.persistence.repositories.reviews import ReviewRepository
from app.infrastructure.persistence.repositories.runs import RunRepository
from app.infrastructure.persistence.repositories.tool_calls import ToolCallRepository


class Repository(
    ConversationRepository,
    RunRepository,
    ArtifactRepository,
    ReviewRepository,
    EventRepository,
    ToolCallRepository,
):
    """聚合所有子仓储的事务门面。

    继承顺序即方法解析顺序（MRO）；所有子仓储共享同一个 ``AsyncSession``
    （由 ``RepositoryBase.__init__`` 注入）。对外表现为一个「无所不能」的仓储，
    内部方法直接复用各聚合仓储的实现。
    """

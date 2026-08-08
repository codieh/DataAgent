"""仓储基类与 ID 生成工具。

提供所有聚合仓储的公共基础：
- ``new_id``：生成带前缀的全局唯一 ID（``{prefix}_{uuid4 hex}``），便于在日志与
  外键中直观区分实体类型。
- ``RepositoryBase``：持有异步 ``AsyncSession``，是所有具体仓储的父类。
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


def new_id(prefix: str) -> str:
    """生成带前缀的唯一 ID。

    形如 ``artifact_9f2c...``，前缀用于标识实体类型（artifact/conv/run/...），
    后缀为 UUID4 的十六进制串，几乎不会冲突。
    """
    return f"{prefix}_{uuid4().hex}"


class RepositoryBase:
    """仓储基类：保存当前会话并供子类复用。

    各聚合仓储通过继承本类并传入同一个 ``AsyncSession``，从而共享事务上下文。
    """

    def __init__(self, session: AsyncSession):
        self.session = session


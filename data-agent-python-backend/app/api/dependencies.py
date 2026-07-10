"""API 层共享依赖定义。

集中声明可复用的 FastAPI 依赖，避免在各个路由文件中重复编写
``Depends(get_session)``。目前提供数据库会话依赖，被所有需要访问持久层的路由使用。
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.database import get_session


# 路由函数只需声明参数类型为 SessionDependency 即可自动注入请求级异步会话
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


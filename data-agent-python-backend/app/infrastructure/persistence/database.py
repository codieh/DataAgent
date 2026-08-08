"""持久化引擎与会话管理（基于 SQLAlchemy 异步）。

职责概览：
- 定义所有 ORM 模型共用的声明基类 ``Base``。
- 根据配置创建异步引擎 ``engine``，并针对 SQLite 在连接建立时设置 WAL 日志
  模式、忙等待超时与开启外键约束。
- 提供 ``get_session`` 异步上下文依赖（供 FastAPI 等框架注入会话）。
- ``initialize_database`` 在启动时建表，并对 SQLite 额外创建两张 FTS5 全文
  检索虚拟表（``result_history_fts``、``conversation_history_fts``），用于
  历史结果与历史对话的模糊/分词搜索（trigram 分词）。
- ``close_database`` 在关闭时释放引擎。

注意：模块导入即创建全局引擎与会话工厂（模块级副作用），因此导入本模块
即有建立数据库目录等副作用，属有意为之。
"""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。

    通过继承 ``DeclarativeBase`` 统一元数据（metadata），各模型定义 ``__tablename__``
    后即可被 ``Base.metadata.create_all`` 自动建表。
    """

    pass


settings = get_settings()
if settings.database_url.startswith("sqlite"):
    database_path = make_url(settings.database_url).database
    if database_path and database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url, future=True)


@event.listens_for(engine.sync_engine, "connect")
def configure_sqlite(dbapi_connection, _connection_record) -> None:
    """针对 SQLite 连接设置性能与一致性相关的 PRAGMA。

    仅对 SQLite 生效；非 SQLite 数据库直接返回。配置项：
    - ``journal_mode=WAL``：写前日志模式，提升并发读写性能。
    - ``busy_timeout=5000``：锁等待 5 秒，降低「database is locked」概率。
    - ``foreign_keys=ON``：开启外键约束（SQLite 默认关闭）。
    """
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# expire_on_commit=False：提交后对象不被过期，避免后续访问触发额外查询。
session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """异步生成数据库会话，供依赖注入使用。

    作为上下文管理器，退出时自动关闭会话（归还连接池），不负责提交。
    """
    async with session_factory() as session:
        yield session


async def initialize_database() -> None:
    """初始化数据库：建表，并在 SQLite 上创建/回填全文检索虚拟表。

    导入 ``models`` 是为了触发所有模型类的定义，确保 ``Base.metadata`` 已收集
    到全部表结构；随后 ``create_all`` 按元数据建表。SQLite 下额外创建两张
    FTS5 虚拟表（trigram 分词，适合子串/模糊匹配），并把已存在的 user/assistant
    消息回填到 ``conversation_history_fts``，便于历史对话搜索。
    """
    from app.infrastructure.persistence import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            # 分析结果历史全文索引：按 dataset/conversation/run 维度索引问题、SQL、列与摘要
            await connection.exec_driver_sql(
                """CREATE VIRTUAL TABLE IF NOT EXISTS result_history_fts USING fts5(
                dataset_id UNINDEXED, conversation_id UNINDEXED, run_id UNINDEXED,
                question, sql, columns, summary, tokenize='trigram')"""
            )
            # 对话历史全文索引：按消息维度索引标题与内容（trigram 分词）
            await connection.exec_driver_sql(
                """CREATE VIRTUAL TABLE IF NOT EXISTS conversation_history_fts USING fts5(
                message_id UNINDEXED, conversation_id UNINDEXED, role UNINDEXED,
                title, content, tokenize='trigram')"""
            )
            # 将既有 user/assistant 消息回填进对话全文索引（去重，避免重复插入）
            await connection.exec_driver_sql(
                """INSERT INTO conversation_history_fts(message_id, conversation_id, role, title, content)
                SELECT m.id, m.conversation_id, m.role, c.title, m.content
                FROM messages m JOIN conversations c ON c.id = m.conversation_id
                WHERE m.role IN ('user', 'assistant')
                  AND NOT EXISTS (
                    SELECT 1 FROM conversation_history_fts f WHERE f.message_id = m.id
                  )"""
            )


async def close_database() -> None:
    """释放异步引擎与底层连接池。"""
    await engine.dispose()

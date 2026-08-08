"""持久化适配器（Persistence adapter）。

本包基于 SQLAlchemy（异步 ``AsyncSession``）实现对平台自身元数据的持久化，
默认使用 SQLite（亦支持其他 SQLAlchemy 兼容数据库）。主要包含：

- ``database``：引擎、会话工厂、Schema 初始化与 SQLite 专属的 FTS 虚拟表。
- ``models``：各聚合根的 ORM 模型定义（对话、消息、运行、阶段、记忆、产物等）。
- ``repositories``：按聚合划分的仓储实现，以及聚合所有仓储的 ``Repository`` 门面。

说明：此处的数据库用于保存「分析平台自身的运行态数据」，与业务数据源
（``datasource`` 包所访问的产品库）是两套独立的存储，切勿混淆。
"""


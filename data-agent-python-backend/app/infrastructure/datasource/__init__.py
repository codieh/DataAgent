"""业务数据源适配器（Business datasource adapters）。

本包负责与外部业务数据库（如产品库）交互，核心职责是以「只读、安全、受限」
的方式访问业务数据：

- 提供数据库结构快照（schema snapshot），供模型理解表与字段。
- 执行经过安全策略校验的只读 ``SELECT`` 查询，并强制行数上限与语句超时。

所有对业务库的写操作均被禁止，SQL 在执行前需通过 ``app.security`` 中的
策略校验（参见 ``sql.py`` 的 ``validate_select_sql``）。
"""


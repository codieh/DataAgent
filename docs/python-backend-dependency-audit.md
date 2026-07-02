# Python 后端依赖与自研边界

> 日期：2026-07-01  
> 原则：通用协议和基础设施优先使用成熟组件；业务契约、分析策略和安全规则由项目维护。

## 当前决策

| 能力 | 决策 | 组件/实现 | 原因 |
| --- | --- | --- | --- |
| LLM Chat Completions API | 使用 SDK | `openai.AsyncOpenAI` | SDK 负责认证、超时、重试、错误类型和响应模型 |
| LLM 结构化输出 | SDK 请求 + 项目类型 | Pydantic Models | 当前兼容端点未确认完整支持 OpenAI Structured Outputs，先在边界严格校验 |
| 工作流与人工中断 | 使用框架 | LangGraph `StateGraph`、`interrupt/Command` | 已覆盖状态机、恢复和检查点需求 |
| Graph Checkpoint | 使用框架 | `AsyncSqliteSaver` | 不自行实现工作流状态持久化 |
| API 与 SSE 输出 | 使用框架 | FastAPI、`StreamingResponse` | 服务端只保留事件协议和持久化补发逻辑 |
| 应用数据访问 | 使用框架 | SQLAlchemy 2、aiosqlite | 项目只维护领域模型和 Repository 查询 |
| 数据库结构读取 | 使用框架 | SQLAlchemy Inspector | 不自行查询各数据库的系统表 |
| SQL 解析 | 使用库 | sqlglot | 项目只维护 SELECT、敏感字段、范围和 LIMIT 等业务策略 |
| BM25 排序 | 暂时保留 | 当前轻量实现 | 仅约 50 行且包含项目所需中英文切词；替换 `rank-bm25` 收益有限，后续统一检索后整体移除 |
| 召回策略 | 项目维护 | Retrieval Service | Top K、知识类型、Schema 事实边界属于核心业务能力 |
| Run/Artifact/Review 契约 | 项目维护 | Pydantic + Repository | 这是前端稳定消费和产品可恢复性的核心 |
| 后台任务注册 | 第一阶段保留 | `TaskRegistry` | 单机桌面应用足够；需要跨进程可靠执行时整体替换为任务队列，不继续扩写自研调度器 |
| 图表建议 | 项目维护契约 | Chart Artifact | 后端只返回图表语义，渲染交给前端 |

## 后续替换触发条件

- 模型服务切换时只替换 `OpenAiChatClient` 配置，工作流继续依赖 `LlmClient`。
- Provider 明确支持原生 Structured Outputs 时，SDK 直接生成 Pydantic 模型，删除 JSON 文本提取兼容层。
- 需要多进程、崩溃后继续执行或任务优先级时，用成熟任务队列替换 `TaskRegistry`。
- 文档量超过本地索引能力或需要在线增量更新时，用正式检索服务替换当前 BM25 文件索引。
- SSE 需要复杂自动重连策略时，前端引入成熟 SSE 客户端；不修改后端事件信封。

## 禁止事项

- 不再手写模型厂商的 HTTP 认证、重试和响应协议。
- 不为了“统一封装”重复包装 SDK 已稳定提供的能力。
- 不用第三方框架替代项目真正需要表达的领域模型和安全规则。
- 引入新依赖前必须说明它删除了哪段自研代码，或解决了哪项已有问题。

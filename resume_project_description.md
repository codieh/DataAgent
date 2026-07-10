# DataAgent Python 后端 — 简历描述（多版本）

## 调查结论

项目核心：基于 FastAPI + LangGraph 构建面向销售数据分析的 AI Agent 后端，支持自然语言查询订单、商品、用户等数据，并生成分析结果。代码规模约 70+ 模块、2000+ 行测试，采用分层架构（API / Application / Domain / Infrastructure）。

技术关键词（供简历 ATS 筛选使用）：Python 3.11, FastAPI, LangGraph, LangChain, OpenAI SDK, Chroma, BM25, RRF, SQLAlchemy, sqlglot, Docker, SQLite, SSE, pytest, uv.

---

## 版本 A：通用技术型（推荐用于大多数投递场景）

> **项目描述**：面向销售数据分析场景的 AI Agent 后端服务，支持用户通过自然语言查询订单、商品、用户行为等数据，并自动生成 SQL 查询、Python 分析和可视化结果。  
> **技术栈**：Python 3.11, FastAPI, LangGraph, LangChain, OpenAI SDK, Chroma, SQLAlchemy, sqlglot, Docker, SQLite, SSE, pytest, uv  
> **核心职责**：
> - 基于 **LangGraph** 构建持久化 Agent 分析工作流，编排输入安全检查、Schema 检索、知识召回、SQL 生成/校验、人工审核、结果总结等 7 个节点，支持运行中断、人工审核后恢复与重试
> - 实现 **Agentic RAG 检索链路**：Chroma 向量召回 + 中文 BM25 词法召回 + RRF 融合排序，覆盖业务文档、证据与数据库 Schema；Schema 检索支持外键关联表自动扩展，保证跨表查询的表完整性
> - 设计多层记忆与上下文压缩机制：会话级持久化摘要（达到 Token 预算 80% 时触发，保留最近 30% 原文）、用户核心记忆（跨会话注入）、SQLite FTS5 历史会话检索，支持 20 万 Token 总上下文窗口的稳定运行
> - 基于 **sqlglot** AST 实现 8 维 SQL 安全策略：仅允许 SELECT、表字段白名单校验、禁止 SELECT * 与危险函数、敏感字段拦截、JOIN 条件检查、行数自动改写，结合 MySQL 只读会话与执行超时，实现生产级 SQL 安全
> - 构建 Docker 隔离的 Python 分析沙箱（无网络、只读根文件系统、降权用户、资源限额与 30 秒超时），支持 LLM 生成代码的复杂数据分析，并设计 SSE 实时事件流与断线续传机制，保证前端分析进度的实时同步

---

## 版本 B：深度工程型（推荐用于技术驱动型公司 / 大厂）

> **项目描述**：企业级销售数据分析 Agent 后端，为桌面端提供自然语言数据查询与智能分析能力。采用分层架构（API / Application / Domain / Infrastructure）与依赖注入，核心链路覆盖 LangGraph 工作流、持久化状态、REST API 与 SSE 实时事件。  
> **技术栈**：Python 3.11, FastAPI, LangGraph, LangChain, OpenAI SDK, Chroma, BM25, RRF, SQLAlchemy, sqlglot, Docker, SQLite, SSE, pytest, uv  
> **核心职责**：
> - 使用 **LangGraph StateGraph** 构建有向分析工作流，定义 7 个节点与 5 组条件边，实现 Agent 工具循环、SQL 安全校验、人工审核中断与恢复的完整状态机；通过 SQLite Checkpoint 实现运行状态的持久化与断点续跑
> - 实现混合知识检索系统：离线阶段对 Markdown/TXT 文档进行标题感知切块与增量向量索引（Chroma + OpenAI Embedding）；在线阶段通过 **BM25 + Chroma 向量 + RRF** 三路融合召回业务文档、证据与实时数据库 Schema，Schema 检索额外做外键邻居扩展，召回准确率显著优于单路向量检索
> - 设计可扩展的上下文管理体系：基于 Token 预算的压力感知摘要器（达到阈值时由 LLM 生成压缩摘要，保留近期原文保证连贯性）、用户核心记忆跨会话注入、历史会话通过 FTS5 按需检索，避免全量历史加载；LLM Client 执行工具结果截断与最终硬上限保护，防止上下文溢出
> - 基于 **sqlglot** 构建确定性 SQL 安全检查引擎（非基于提示词）：将模型生成的 SQL 解析为 AST，依次执行单语句 SELECT 校验、系统表拦截、危险函数/变量检测、SELECT * 拦截、表字段白名单、JOIN 条件完备性、敏感字段聚合校验、LIMIT 自动改写等 8 层检查，拦截率近 100% 且支持可重试/不可重试分类
> - 实现 Python 复杂分析沙箱：基于 Docker 构建一次性隔离容器（无网络、只读根文件系统、丢弃全部 Linux Cap、以 nobody 用户运行、限制 CPU/内存/PID 与 30 秒超时），SQL 结果通过只读卷挂载进沙箱，执行结果与日志受控回传；同时实现 SSE 事件流服务器，支持 `after_seq` / `Last-Event-ID` 断线续传与心跳保活，确保弱网环境下的实时进度同步
> - 建立完整的可观测性与测试体系：结构化日志贯穿 requestId / runId / Token 用量，各阶段耗时落库；pytest 测试覆盖 LangGraph 工作流、Checkpoint、持久化、REST API、SSE 流、安全策略与提示注入防御等核心链路，测试代码约 2000+ 行

---

## 版本 C：偏安全/企业级（推荐用于金融科技、企业 SaaS 等安全敏感场景）

> **项目描述**：面向销售场景的企业级 AI 数据分析平台后端，核心解决自然语言到 SQL 的生成与执行安全、LLM 生成代码的隔离执行、以及长会话上下文稳定性问题。  
> **技术栈**：Python 3.11, FastAPI, LangGraph, LangChain, OpenAI SDK, Chroma, SQLAlchemy, sqlglot, Docker, SQLite, SSE, pytest  
> **核心职责**：
> - 基于 **LangGraph** 构建带安全熔断机制的 Agent 工作流：输入安全检查节点拦截提示注入；SQL 生成后强制进入 sqlglot AST 安全校验节点，通过后方可执行；支持人工审核中断，审核通过/驳回后工作流恢复或重规划
> - 构建生产级 SQL 安全体系：使用 **sqlglot** 将模型生成 SQL 解析为 AST，实施 8 层确定性校验（语句类型、系统表、危险函数、SELECT *、Schema 白名单、JOIN 条件、敏感字段、行数上限），自动改写缺失/超限 LIMIT；数据库层使用仅拥有 SELECT 权限的专用账号，形成双层防御
> - 实现 Docker 隔离的 Python 代码执行沙箱：LLM 生成的数据分析脚本在一次性容器中运行，完全禁用网络、根文件系统只读、丢弃全部 Linux 权限能力、以 nobody 用户运行，限制内存/CPU/PID 与 30 秒执行超时，防止不可信代码对宿主造成任何影响
> - 设计多层会话记忆与上下文安全机制：持久化对话摘要（Token 预算 80% 触发，保留 30% 近期原文）、用户核心记忆跨会话注入、历史会话 FTS5 检索；对单条工具结果施加 20K Token 截断与 200K 总上下文硬上限，防止超长上下文导致的模型性能衰减与成本失控
> - 构建支持断线续传的 SSE 实时事件流：前端通过 `/runs/{id}/events` 订阅分析进度，支持 `after_seq` 与 `Last-Event-ID` 参数实现断线后从上次位置续传，配合心跳保活机制，保证弱网与移动端环境下的实时体验

---

## 简历书写要点说明（为什么这样写）

| 要点 | 说明 | 本项目的体现 |
|------|------|-----------|
| **动词开头** | 每条 bullet point 用"设计/实现/构建/优化"等强动词开头 | "基于 LangGraph 构建..."、"实现混合知识检索系统..." |
| **量化成果** | 尽量用数字说话，即使不是业务指标，也要用技术参数 | "7 个节点与 5 组条件边"、"8 维 SQL 安全策略"、"20 万 Token 上下文"、"30 秒超时"、"2000+ 行测试" |
| **技术关键词** | 让简历能被 ATS（自动筛选系统）命中 | 显式列出 FastAPI、LangGraph、Chroma、sqlglot、RRF、SSE 等 |
| **突出难点与解决方案** | 不要只写"做了什么"，要写"解决了什么难题" | 不写成"用了 Docker"，而是"构建 Docker 隔离沙箱，解决 LLM 生成代码的不可信执行问题" |
| **区分"确定性"与"LLM 判断"** | 安全/企业级简历中，强调"AST 确定性校验"而非"让模型判断安全" | "基于 sqlglot AST 实现 8 维 SQL 安全策略"——突出这不是依赖提示工程的方案 |
| **控制长度** | 每条 bullet 不超过 3-4 行，太长会被跳过 | 每个版本都控制在 5 条以内，每条精炼 |
| **场景适配** | 不同公司关注点不同，准备多个版本 | 通用型（广度）、工程型（深度）、安全型（防御） |

---

## 可选的补充数据（如果简历有空间可以加上）

- 架构模式：分层架构（API / Application / Domain / Infrastructure），依赖注入，Repository 模式
- 性能与稳定性：Agent 默认最多循环 6 次、执行 3 条 SQL、修复 2 次，避免开放式循环无限消耗 Token
- 可观测性：HTTP 请求级日志（X-Request-ID）、LLM 调用日志（runId / Token 用量 / 耗时）、阶段耗时统计
- 数据演示：内置 CLI 生成 5,000 用户 / 200 商品 / 50,000 订单的演示数据，支持快速验证

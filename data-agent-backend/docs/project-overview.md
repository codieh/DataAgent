# 📘 `data-agent-backend` 项目梳理

## 1. 项目定位

`data-agent-backend` 是一个**精简版数据分析 Agent 后端**。

它的目标不是先做成完整平台，而是先把一条清晰、可运行、可观察的主链路跑通：

> 用户自然语言问题 → 识别意图 → 召回证据/Schema → 生成 SQL → 执行 SQL → 返回结果

当前项目更准确的定位是：

- ✅ 一个 **流式 NL2SQL Agent Backend**
- ✅ 一个 **具备初步检索基础设施的 V1.5 后端**
- ❌ 还不是完整的 Agent 平台

---

## 2. 项目当前解决的问题

这个项目主要解决下面这类问题：

- “查询销量最高的 10 个商品”
- “统计每个分类的销售额”
- “查询购买过智能手机的用户”
- “查询库存低于 20 的商品”

系统会自动完成：

1. 判断是不是数据分析问题
2. 找相关业务证据
3. 找相关库表字段
4. 对问题做增强改写
5. 生成 SQL
6. 执行 SQL
7. 生成结果总结

---

## 3. 整体架构概览 🧱

当前项目大致可以分成 4 层：

### 3.1 接口层

负责接收请求、返回 SSE、暴露索引管理接口。

核心文件：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\controller\SearchLiteController.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\controller\RecallIndexController.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\controller\DbPingController.java`

### 3.2 编排层

负责决定流水线步骤如何顺序执行。

核心文件：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\SearchLiteOrchestrator.java`

作用：

- 顺序执行各个 step
- 聚合流式消息
- 错误兜底
- 输出完整 SSE 流

### 3.3 状态层

负责在不同 step 之间共享上下文数据。

核心文件：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\api\lite\SearchLiteState.java`

它会保存：

- 原始 query
- intent 结果
- evidence
- schema
- recalled schema
- canonicalQuery
- sql
- rows
- summary

### 3.4 能力层

每个 step 实现一段具体能力。

目录：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\step\impl`

---

## 4. 当前主链路 🔄

当前搜索主链路是：

```text
INTENT
  -> EVIDENCE
  -> SCHEMA
  -> SCHEMA_RECALL
  -> ENHANCE
  -> SQL_GENERATE
  -> SQL_EXECUTE
  -> RESULT
```

### 4.1 INTENT（实现时间：2026-03-22 22:21）

作用：

- 判断是不是数据分析问题

核心实现：

- `IntentMinimaxStep`

### 4.2 EVIDENCE（实现时间：2026-03-23 13:11）

作用：

- 召回业务知识、指标口径、说明文档等文本证据

核心实现：

- `EvidenceFileStep`

### 4.3 SCHEMA（实现时间：2026-03-24 17:03）

作用：

- 获取数据库表/列/外键信息

核心实现：

- `SchemaMysqlIntrospectStep`

### 4.4 SCHEMA_RECALL（实现时间：2026-03-24 17:48）

作用：

- 从全量 schema 中找本次问题最相关的表和列

核心实现：

- `SchemaRecallStep`

### 4.5 ENHANCE（实现时间：2026-03-24 19:10）

作用：

- 把 query 改写成更适合生成 SQL 的形式

核心实现：

- `EnhanceMinimaxStep`

### 4.6 SQL_GENERATE（实现时间：2026-03-24 18:07）

作用：

- 基于 query + evidence + schema 生成 SQL

核心实现：

- `SqlGenerateMinimaxStep`

### 4.7 SQL_EXECUTE（实现时间：2026-03-24 18:31）

作用：

- 对 SQL 做安全处理并执行查询

核心实现：

- `SqlExecuteJdbcStep`

### 4.8 RESULT（实现时间：2026-03-24 18:48）

作用：

- 对结果集做自然语言总结

核心实现：

- `ResultMinimaxStep`

---

## 5. 当前已经做好的核心能力 ✅

### 5.1 SSE 流式输出（实现时间：2026-03-22 16:54）

已经支持流式接口和阶段化输出。

主接口：

- `GET /api/stream/search-lite`

### 5.2 真流式 LLM 接入（首个真实接入时间：2026-03-22 22:21）

已经接入 MiniMax，支持这些阶段的真实流式能力：

- 意图识别
- Query Enhance
- SQL Generate
- Result Summary

### 5.3 真实数据库执行（接库时间：2026-03-24 11:01，执行闭环完成：2026-03-24 18:31）

已经可以连接 `product_db` 执行真实 SQL。

### 5.4 SQL 安全基础控制（实现时间：2026-03-24 18:31）

已经具备基础 guardrails，例如：

- 只读限制
- 单语句限制
- limit 控制
- 执行错误兜底

### 5.5 可观测性（首轮日志增强：2026-03-24 14:04，recall 日志增强：2026-03-25 19:20 后继续完善）

当前已经有：

- 编排层日志
- LLM 日志
- DB 日志
- SSE 生命周期日志
- recall 命中日志
- 索引生命周期日志
- hybrid 分数拆解日志

### 5.6 基础测试（实现时间：2026-03-24 20:05）

已经有：

- mock pipeline 串测
- orchestrator 异常回归
- recall 相关测试
- vector recall 基础测试

---

## 6. Recall 检索基础设施（当前重点）🔍

这是项目当前最有“Agent 味道”的一层。

目录：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall`

### 6.1 已有能力（统一 recall 基础设施起步：2026-03-25 19:20 所在批次，前置持久化索引与状态接口已在同日逐步补齐）

#### 统一文档模型

- `RecallDocument`
- `RecallHit`
- `RecallOptions`

#### 索引构建

- `EvidenceIndexBuilder`
- `SchemaIndexBuilder`

#### 召回引擎

- `KeywordRecallEngine`
- `VectorRecallEngine`
- `HybridRecallEngine`

#### 统一服务

- `RecallService`

#### 本地持久化

- `FileRecallDocumentStore`

### 6.2 索引管理接口（实现时间：2026-03-25）

当前支持：

- `POST /api/index/init/evidence`
- `POST /api/index/init/schema`
- `POST /api/index/init/all`
- `GET /api/index/status`

### 6.3 当前持久化方式（实现时间：2026-03-25）

当前索引会落到本地文件：

- `D:\GitHub\DataAgent\data-agent-backend\data\recall\evidence-index.json`
- `D:\GitHub\DataAgent\data-agent-backend\data\recall\schema-index.json`

---

## 7. 向量化做到哪里了 🧠

当前已经有“向量化起步版”，但还不是完全成熟版。

### 7.1 已完成（实现时间：2026-03-25 19:20）

- 已接入本地 embedding 接口
- 支持 OpenAI-compatible embeddings 协议
- 支持为 recall 文档补 embedding
- 支持 vector recall
- 支持 hybrid recall

核心文件：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\embedding\LocalEmbeddingClient.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\RecallEmbeddingService.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\VectorRecallEngine.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\HybridRecallEngine.java`

### 7.2 当前本地配置（接入时间：2026-03-25 19:20）

当前默认对接：

- Base URL: `http://localhost:11434`
- Model: `bge-m3`
- Path: `/v1/embeddings`

### 7.3 当前状态（持续修正运行问题：2026-03-25 晚间）

- 架构已接好
- 本地 embedding 可接入
- 已有降级策略（embedding 不可用时回退关键词召回）
- 但还没有做系统化效果评测

---

## 8. 当前接口清单 🌐

### 8.1 搜索接口（实现时间：2026-03-22 21:38）

- `GET /api/stream/search-lite`

### 8.2 索引接口（实现时间：2026-03-25）

- `POST /api/index/init/evidence`
- `POST /api/index/init/schema`
- `POST /api/index/init/all`
- `GET /api/index/status`

### 8.3 其他辅助接口（DB Ping：2026-03-24 11:01；SSE Ping：2026-03-22 16:54）

- `GET /api/db/ping`
- `GET /api/stream/ping`

---

## 9. 文档与评测准备 📚

### 9.1 数据设计文档（实现时间：2026-03-25 11:16）

- `D:\GitHub\DataAgent\data-agent-backend\docs\product-data-rich-design.md`

内容包括：

- 增强版 `product_db` 数据设计
- 数据分布
- 多对多分类设计
- 订单与金额口径一致性要求

### 9.2 评测题库（实现时间：2026-03-25 11:16；评测系统 TODO 后续补充：2026-03-25）

- `D:\GitHub\DataAgent\data-agent-backend\docs\eval-question-bank.md`

内容包括：

- 功能题
- 风险题
- 安全题
- 意图题
- 首轮回归集
- 评测系统 TODO

---

## 10. 当前项目版本判断 🏷️

如果按版本来描述，当前我建议这样理解：

### V1（2026-03-24）

- 流式 NL2SQL 主链路跑通

### V1.5（2026-03-25，当前）

- recall 基础设施成型
- 本地索引持久化可用
- 向量化起步版接入
- 评测题库和增强数据已准备

也就是说，当前项目最准确的定位是：

> **V1.5：主链路完成，检索基础设施初步成型，开始进入评测与优化阶段。**

---

## 11. 还没做完的关键部分 🛠️

当前主要还差这些：

### 11.1 真正的评测系统

虽然题库已经有了，但还没有真正实现成代码模块：

- dataset
- evaluator
- metrics
- report

### 11.2 向量召回效果验证

虽然接好了 embedding 和 hybrid recall，但还没正式量化：

- 是否比纯 keyword 更准
- 哪些题提升明显
- 哪些题仍然失败

### 11.3 多轮会话能力

当前仍然主要是单轮分析流程。

### 11.4 多数据源 / 多 Agent 配置化

当前主要围绕 `product_db`，还没有真正配置化。

---

## 12. 当前最重要的几个入口文件 🧭

如果后面想快速找回项目感觉，优先看下面这些文件：

### 主链路入口

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\controller\SearchLiteController.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\SearchLiteOrchestrator.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\api\lite\SearchLiteState.java`

### recall 基础设施入口

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\RecallService.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\HybridRecallEngine.java`
- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\recall\embedding\LocalEmbeddingClient.java`

### 文档入口

- `D:\GitHub\DataAgent\data-agent-backend\docs\eval-question-bank.md`
- `D:\GitHub\DataAgent\data-agent-backend\docs\product-data-rich-design.md`
- `D:\GitHub\DataAgent\data-agent-backend\docs\project-overview.md`

---

## 13. 下一步最推荐做什么 🚀

如果继续推进项目，我最推荐的是：

### 13.1 优先做评测系统代码化

也就是把已经有的题库和思路，真正实现成：

- `dataset`
- `evaluator`
- `metrics`
- `report`

### 13.2 再做向量召回效果验证

重点回答：

- hybrid recall 是否优于 keyword recall
- 哪些题提升了
- 哪些题仍然失败

### 13.3 最后再考虑更重的功能

例如：

- 多轮会话
- 多数据源
- PostgreSQL / pgvector
- 更完整的平台能力

---

## 14. 一句话总结 💡

这个项目现在已经不是“能跑的 demo”，而是：

> **一个具备流式 NL2SQL 主链路、初步检索基础设施、向量化起步能力和评测准备工作的数据分析 Agent 后端。**

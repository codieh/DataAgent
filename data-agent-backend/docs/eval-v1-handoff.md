# Eval V1 交接说明

## 1. 目标

本分支用于构建 `data-agent-backend` 的轻量评测系统 V1。

这次工作的目标不是搭一个重型评测平台，而是先补齐一套 **可运行、可记录、可比较** 的评测闭环，帮助我们验证当前项目的核心能力，并为后续简历中的量化表达提供依据。

评测系统 V1 主要服务于以下能力验证：

- Graph 编排主链是否稳定
- 多轮上下文 V1 是否有效
- RAG / Schema / SQL 主链是否可观测
- SQL 重试与结果分流是否按预期工作

---

## 2. 当前项目已有能力

在开始评测系统开发前，需要先知道当前主链已经具备的能力：

- `SearchLite` 已迁移为 Graph 主链
- 已具备条件路由：
  - `Intent`
  - `SchemaRecall`
  - `SqlGenerate`
  - `SqlExecute`
- 已具备多轮上下文 V1：
  - 基于 `threadId` 的窗口式历史
  - `multiTurnContext`
  - `contextualizedQuery`
- 已具备结果分流与 SQL 重试：
  - `no_schema`
  - `no_sql`
  - `execution_error`
  - `success`
- 已具备多知识源使用能力：
  - `schema`
  - `evidence`
  - `document`

因此，评测系统 V1 的重点不是继续改主链，而是验证这些能力是否真实有效。

---

## 3. 本分支要做什么

本分支应聚焦在以下 4 件事：

- 定义评测样例格式
- 实现样例跑批入口
- 输出结构化评测结果
- 统计基础指标并生成报告

推荐优先覆盖三类样例：

- 单轮分析问题
- 多轮追问问题
- 异常 / 失败 / fallback 场景

---

## 4. 本分支不要做什么

为了避免发散，评测分支先不要做以下事情：

- 不重构主链业务逻辑
- 不继续扩展 Graph 主链功能
- 不引入重型评测框架
- 不引入复杂 LLM-as-a-judge 平台
- 不顺手做向量数据库迁移
- 不扩展成通用实验平台

如果需要做更高级的评测能力，应放到后续 V2 / V3。

---

## 5. 建议复用的已有文档

新线程启动后，建议先阅读这些文档：

- `D:\GitHub\DataAgent\data-agent-backend\docs\graph-migration-notes.md`
- `D:\GitHub\DataAgent\data-agent-backend\docs\document-rag-design.md`
- `D:\GitHub\DataAgent\data-agent-backend\docs\eval-question-bank.md`
- `D:\GitHub\DataAgent\data-agent-backend\docs\project-overview.md`

其中：

- `graph-migration-notes.md`：理解当前 Graph 主链与多轮上下文
- `document-rag-design.md`：理解当前知识使用策略
- `eval-question-bank.md`：可作为样例集设计参考

---

## 6. 建议的目录落点

建议评测系统 V1 落在以下位置：

- 样例集：
  - `D:\GitHub\DataAgent\data-agent-backend\data\eval\`
- 跑批代码：
  - `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\eval\`
- 报告输出：
  - `D:\GitHub\DataAgent\data-agent-backend\data\eval-reports\`

如果需要测试代码，可放到：

- `D:\GitHub\DataAgent\data-agent-backend\src\test\java\com\alibaba\cloud\ai\dataagentbackend\lite\eval\`

---

## 7. 建议记录的核心字段

每条评测样例跑完后，建议至少记录：

- `caseId`
- `query`
- `threadId`
- `history`
- `intentClassification`
- `recalledTables`
- `sql`
- `sqlRetryCount`
- `resultMode`
- `rowCount`
- `summary`
- `error`

如果可以，进一步记录：

- `recalledDocuments`
- `recalledEvidences`
- `canonicalQuery`
- `contextualizedQuery`

---

## 8. V1 建议先做的指标

建议第一版先做这些基础指标：

- `intent_correct`
- `schema_recall_hit`
- `sql_generated`
- `sql_executed`
- `result_mode_expected`
- `multi_turn_followup_correct`

如果资源允许，再补两个标签：

- `knowledge_hallucination`
- `reasoning_hallucination`

这里只需要做到：

- 能记录
- 能导出
- 能人工/规则混合判断

不需要一步做到全自动智能评测。

---

## 9. 验收标准

评测系统 V1 完成时，至少应满足：

- 可以读取固定样例集
- 可以批量执行样例
- 可以输出结构化结果
- 可以生成一份基础报告
- 可以看出：
  - 哪些样例成功
  - 哪些失败
  - 失败发生在哪个链路阶段

---

## 10. 简历价值

这套评测系统完成后，可以支持后续简历表达：

- 构建轻量评测体系，对 Graph 编排、多轮上下文、RAG 与 NL2SQL 主链效果进行验证
- 设计基础指标与测试样例集，支撑系统从功能可用走向效果可量化
- 在自主评估体系中记录知识幻觉与推理幻觉，辅助定位检索与生成链路问题

---

## 11. 新线程建议启动提示词

可直接将下面这段话发给新的 Codex 线程：

> 当前仓库为 `D:\GitHub\DataAgent`，请在 `codex/eval-v1` 分支上开发轻量评测系统 V1。  
> 先阅读：  
> - `D:\GitHub\DataAgent\data-agent-backend\docs\graph-migration-notes.md`  
> - `D:\GitHub\DataAgent\data-agent-backend\docs\document-rag-design.md`  
> - `D:\GitHub\DataAgent\data-agent-backend\docs\eval-question-bank.md`  
> - `D:\GitHub\DataAgent\data-agent-backend\docs\eval-v1-handoff.md`  
> - `D:\GitHub\DataAgent\data-agent-backend\docs\eval-v1-todo.md`
>
> 目标：  
> - 构建固定样例集  
> - 实现跑批执行  
> - 输出评测结果  
> - 统计基础指标  
>
> 注意：  
> - 不重构主链  
> - 不引入重型评测框架  
> - 优先做可运行、可记录、可比较的 V1


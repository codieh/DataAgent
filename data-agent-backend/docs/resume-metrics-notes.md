# Backend Resume Metrics Notes

这份文档用于记录 `data-agent-backend` 项目的简历量化点、后续评测方案和可直接复用的简历表述模板。

当前状态：
- 指标口径先定义清楚
- 数值暂不填写
- 后续基于实际 `eval` / `trace` 结果补齐

## 1. 建议优先量化的指标

### 1.1 召回效果

适合对比：
- `bm25`
- `hybrid`
- `bm25-pgvector-rerank`

建议指标：
- `Top1` 命中率
- `Top3` 命中率
- `Top5` 命中率
- `MRR`
- `nDCG`

适合写进简历的表达：
- 混合召回替换纯 `BM25` 后，知识召回 `Top5` 命中率提升 `X%`
- 引入 `pgvector + rerank` 后，业务术语和表字段召回精度提升 `Y%`

### 1.2 SQL 生成效果

建议指标：
- 首轮 SQL 可执行率
- 最终 SQL 可执行率
- 首轮 SQL 正确率
- 最终任务成功率

适合写进简历的表达：
- 引入 `Schema Recall` 后，首轮 SQL 可执行率从 `A%` 提升到 `B%`
- 引入 `Query Enhance` 后，复杂查询最终成功率提升 `X%`

### 1.3 多轮对话效果

建议指标：
- 多轮追问成功率
- 指代消解成功率
- 上下文补全成功率

适合写进简历的表达：
- 基于 `threadId` 的上下文管理机制，使多轮追问类问题成功率提升 `X%`

### 1.4 上下文压缩效果

建议指标：
- `schemaText` 长度
- `recalledSchemaText` 长度
- Prompt token 数
- 平均输入上下文压缩比例

适合写进简历的表达：
- 通过 `Schema Recall` 聚焦相关表和字段，将 SQL 生成阶段的上下文长度降低 `X%`

### 1.5 时延指标

建议指标：
- 首字返回时间
- 端到端总耗时
- Recall 耗时
- SQL 执行耗时

适合写进简历的表达：
- 基于 `WebFlux + SSE` 实现流式返回，将复杂查询的首字返回时间控制在 `Xs` 内

### 1.6 安全治理效果

建议指标：
- 敏感字段拦截率
- `SELECT *` 拦截率
- 宽表导出拦截率
- 高风险 SQL 误执行率

适合写进简历的表达：
- 设计 SQL Guard 策略，对敏感字段直查和宽表导出类请求实现 `100%` 拦截

## 2. 这个项目最值得补的数据对比实验

建议至少做 4 组对比。

### 2.1 召回策略对比

变量：
- `search.lite.recall.provider=bm25`
- `search.lite.recall.provider=hybrid`
- `search.lite.recall.provider=bm25-pgvector-rerank`

观察指标：
- `TopK` 命中率
- SQL 可执行率
- 端到端成功率

### 2.2 是否启用 Schema Recall

变量：
- 使用全量 schema
- 使用 `Schema Recall`

观察指标：
- Prompt 长度
- 首轮 SQL 可执行率
- 最终成功率

### 2.3 是否启用 Query Enhance

变量：
- `enhance.provider=mock/关闭`
- `enhance.provider=minimax`

观察指标：
- 多轮追问成功率
- SQL 首轮正确率

### 2.4 单步执行 vs 多步 Planner

变量：
- 单步 SQL
- `planner + plan executor`

观察指标：
- 复杂问题完成率
- 平均总耗时
- 失败修复成功率

## 3. 现有可用评测入口

仓库里已经有可复用的评测和追踪能力：

- 评测代码目录：
  - `data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval`
- 评测数据目录：
  - `data-agent-backend/data/eval/cases`
- 现有评测文档：
  - `data-agent-backend/docs/eval-v1-design.md`
  - `data-agent-backend/docs/eval-question-bank.md`
  - `data-agent-backend/docs/eval-v1-implementation-walkthrough.md`
- Trace 目录：
  - `data/traces`
  - `data-agent-backend/data/traces`

后续补数值时，优先复用这些现成能力，不要手工拍脑袋估算。

## 4. 建议最终沉淀的一张对比表

后续补数据时，建议统一整理成下面这种表。

| 优化项 | 指标 | 优化前 | 优化后 | 提升 |
|---|---:|---:|---:|---:|
| 纯 BM25 -> 混合召回 | Top5 命中率 |  |  |  |
| 全量 Schema -> Schema Recall | 首轮 SQL 可执行率 |  |  |  |
| 无 Enhance -> Query Enhance | 多轮追问成功率 |  |  |  |
| 单步执行 -> Planner 多步执行 | 复杂任务完成率 |  |  |  |
| 无 Guard -> SQL Guard | 高风险 SQL 误执行率 |  |  |  |

## 5. 简历写法模板

### 5.1 有实测数据时

- 负责 AI 数据分析 Agent 后端研发，基于 `Spring Boot + WebFlux + Spring AI Alibaba Graph` 搭建 NL2SQL 工作流，支持意图识别、知识召回、Schema 聚焦、SQL 生成执行与结果总结的全链路流式返回。
- 设计 `BM25 + pgvector + rerank` 混合召回链路，在离线评测集上将知识召回 `Top5` 命中率提升 `X%`，带动首轮 SQL 可执行率提升 `Y%`。
- 实现 `Schema Recall + Query Enhance` 机制，将 SQL 生成阶段上下文长度压缩 `X%`，复杂查询成功率提升 `Y%`。
- 设计多步规划、人工审核、SQL 重试与安全拦截机制，将高风险 SQL 误执行率降低至 `X%`，提升系统可控性与执行安全。

### 5.2 暂时没有实测数据时

- 负责 AI 数据分析 Agent 后端研发，基于 `Spring Boot + WebFlux + Spring AI Alibaba Graph` 搭建面向自然语言数据查询的 Agent 工作流。
- 设计混合召回、Schema Recall 与 Query Enhance 链路，重点优化复杂查询场景下的知识命中率、SQL 可执行性和结果稳定性。
- 引入多步规划、人工审核、SQL 重试与安全拦截机制，增强 Agent 在真实业务环境中的可控性与安全性。

## 6. 后续补数据时的注意事项

- 所有数字必须来自真实评测、日志、trace 或固定测试集。
- 不要混用不同数据集的指标。
- 如果是离线评测结果，简历中最好明确写成“在离线评测集上”。
- 如果是 Demo 数据库结果，不要表述成线上生产指标。
- 如果某项提升来自多项优化叠加，面试时要说清楚主因，不要把所有收益都归给单一改动。


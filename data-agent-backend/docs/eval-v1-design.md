# Eval V1 设计记录

## 1. 目标

这份文档记录轻量评测系统 V1 的关键设计决策，保证实现保持：

- 轻量
- 清晰
- 可运行
- 可对比

本轮重点不是做通用实验平台，而是先补齐：

- 固定样例集
- 跑批执行入口
- 结构化结果输出
- 基础指标与 Markdown 报告

## 2. 样例格式

V1 使用统一 JSON dataset 格式，位置：

- `D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\*.json`

顶层结构：

```json
{
  "datasetId": "single-turn-v1",
  "version": "eval-v1",
  "description": "dataset description",
  "cases": []
}
```

每条 case 结构重点字段：

- `caseId`
- `title`
- `category`
- `scenarioType`
- `query`
- `history`
- `expectations`

### 2.1 为什么保留 `history`

多轮评测不是直接把上一轮文本拼进 `query`，而是：

- 用同一个 `threadId`
- 顺序回放 `history`
- 再执行当前目标 query

这样才能真实复用当前主链里的：

- `MultiTurnContextManager`
- `multiTurnContext`
- `contextualizedQuery`

### 2.2 为什么 expectations 保持轻量

V1 只做规则可判的字段，不直接接 LLM-as-a-judge。

当前 expectations 主要覆盖：

- `expectedIntent`
- `expectedTables`
- `expectedResultMode`
- `expectedSqlGenerated`
- `expectedSqlExecuted`
- `expectedSqlRetryCount`
- `expectedContextualizedQueryContains`

## 3. 跑批执行策略

Runner 直接复用：

- `SearchLiteOrchestrator`

没有绕开主链，也没有额外拼一套假的 pipeline。

同时为评测增加了一个很小的执行辅助能力：

- `SearchLiteOrchestrator.runForEvaluation(...)`

它会在不改变原有 SSE 行为的前提下，回收：

- 最终 `SearchLiteState`
- 执行产生的 `SearchLiteMessage` 列表
- 总耗时

这样评测系统就不需要从 SSE 文本里硬解析：

- `intentClassification`
- `recalledTables`
- `sql`
- `sqlRetryCount`
- `resultMode`
- `summary`

## 4. 报告输出策略

输出目录：

- `D:\GitHub\DataAgent\data-agent-backend\data\eval-reports\`

每次跑批会同时产出：

- `latest-report.json`
- `latest-report.md`
- 带时间戳归档文件

这样兼顾：

- 固定“最新结果”查看
- 历史结果对比

## 5. 指标定义

V1 先统计 6 个指标：

- `intentAccuracy`
- `schemaRecallHitRate`
- `sqlGenerationRate`
- `sqlExecutionSuccessRate`
- `resultModeAccuracy`
- `multiTurnFollowupAccuracy`

说明：

- `intentAccuracy`
  - 只统计配置了 `expectedIntent` 的 case
- `schemaRecallHitRate`
  - 只统计配置了 `expectedTables` 的 case
- `sqlGenerationRate`
  - 统计实际生成 SQL 的 case 比例
- `sqlExecutionSuccessRate`
  - 统计实际执行成功的 case 比例
- `resultModeAccuracy`
  - 只统计配置了 `expectedResultMode` 的 case
- `multiTurnFollowupAccuracy`
  - 只统计 `scenarioType=multi_turn` 且配置了 `expectedContextualizedQueryContains` 的 case

## 6. 当前边界

V1 暂不做：

- 结果集与标准 SQL 的自动比对
- LLM 总结质量评判
- 幻觉自动识别
- 通用实验平台抽象
- 多版本对战系统

当前优先级明确是：

> 先做一套可执行、可记录、可比较的轻量闭环。

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
  "suite": "standard",
  "description": "dataset description",
  "cases": []
}
```

其中 `suite` 用于支持评测分层。

当前约定：

- `quick`
  - 快速回归集
- `golden`
  - 人工校准的核心黄金集
- `standard`
  - 标准评测集
- `all`
  - runner 层支持的聚合模式，表示同时跑全部 suite

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

新版本报告还会额外输出：

- dataset summary
- scenario summary
- diagnostic status breakdown
- failure breakdown

## 5. 指标定义

V1 先统计 11 个指标：

- `expectationPassRate`
- `intentAccuracy`
- `failureFallbackAccuracy`
- `unexpectedSqlGenerationBlockRate`
- `unexpectedSqlExecutionBlockRate`
- `sqlReferenceAccuracy`
- `resultSignatureAccuracy`
- `schemaRecallHitRate`
- `sqlGenerationRate`
- `sqlExecutionSuccessRate`
- `resultModeAccuracy`
- `multiTurnFollowupAccuracy`

同时 runner 现在支持按 suite 过滤 dataset。

推荐用法：

- 日常做可信基准核验先跑 `golden`
- 日常改动后先跑 `quick`
- 功能稳定后跑 `standard`
- 需要全量对比时跑 `all`

说明：

- `expectationPassRate`
  - 统计 case 是否整体满足当前 expectations，用来表示更接近“答对率”的指标
- `intentAccuracy`
  - 只统计配置了 `expectedIntent` 的 case
- `failureFallbackAccuracy`
  - 只统计 `scenarioType=failure_fallback` 的 case，看整体 expectation 是否通过
- `unexpectedSqlGenerationBlockRate`
  - 只统计 `failure_fallback` case，看“不应生成 SQL”的样例是否真的没生成
- `unexpectedSqlExecutionBlockRate`
  - 只统计 `failure_fallback` case，看“不应执行 SQL”的样例是否真的被拦截
- `sqlReferenceAccuracy`
  - 只统计配置了 `referenceSql` 或 `expectedSqlContains` 的 case，看生成 SQL 是否满足参考约束
- `resultSignatureAccuracy`
  - 只统计配置了 `expectedRowCount` 或 `expectedSummaryContains` 的 case，看结果特征是否满足预期
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

运行入口也支持更直接的短参数：

- `--suite=quick`
- `--suite=golden`
- `--suite=standard`
- `--suite=all`

内部会自动转成 Spring 属性 `search.lite.eval.suite`。

## 5.1 标准答案骨架

V1 先不做重型结果对拍平台，但现在样例格式已经支持轻量“标准答案”表达：

- `referenceSql`
  - 用于标准 SQL 的规范化等价匹配
- `expectedSqlContains`
  - 用于 SQL 关键片段约束
- `expectedRowCount`
  - 用于结果行数特征约束
- `expectedSummaryContains`
  - 用于总结文本特征约束

这样后续可以按题型渐进增强，而不是一次把所有 case 都抬成重平台。

## 5.2 核心黄金集

当前已经新增第一批 `golden-core-v1`，位置：

- `D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\golden-core.json`

首批黄金集控制在 6 题，刻意覆盖三类高价值能力：

- 单轮分析
  - `GC01` 订单状态聚合
  - `GC02` 六月订单趋势
  - `GC03` 天气闲聊边界
- 多轮追问
  - `GC04` 高消费用户追问下单次数
- failure / fallback
  - `GC05` 仓库表缺失
  - `GC06` 危险 SQL 注入

这批样例的目标不是先追求覆盖面，而是先建立一块更可信的评测锚点。

## 6. 当前边界

V1 暂不做：

- 结果集与标准 SQL 的自动比对
- LLM 总结质量评判
- 幻觉自动识别
- 通用实验平台抽象
- 多版本对战系统

当前优先级明确是：

> 先做一套可执行、可记录、可比较的轻量闭环。

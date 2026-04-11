# Eval V1 实现细节说明

## 1. 为什么这套系统已经算“可用”

这套轻量评测系统 V1 的价值，不在于它已经能自动判断所有答案对错，
而在于它已经把评测这件事从：

- 手工提问
- 看日志
- 凭感觉判断

推进成了一条可以重复执行的工程链路：

- 固定样例集
- 批量执行
- 结构化结果
- 指标统计
- Markdown 报告

也就是说，
即使它今天还不完美，
它已经能稳定回答下面这些问题：

- 这一版总共跑了多少题
- 哪些题失败了
- 失败集中在哪些能力
- 是 intent、schema recall、multi-turn、SQL 还是 fallback 出的问题

这就是“可用”的关键标准。

---

## 2. 实现总览

当前实现分成 5 层：

1. `dataset`
   - 定义评测样例格式
2. `runner`
   - 顺序执行样例
3. `result`
   - 抽取并保存每题的结构化结果
4. `metrics`
   - 计算基础指标
5. `report`
   - 输出 JSON / Markdown 报告

主要代码目录：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\eval`

主要数据目录：

- `D:\GitHub\DataAgent\data-agent-backend\data\eval`
- `D:\GitHub\DataAgent\data-agent-backend\data\eval-reports`

---

## 3. 样例数据是怎么设计的

### 3.1 数据集结构

样例不是一题一个零散 JSON，
而是按 dataset 分文件组织。

例如：

- `single-turn.json`
- `multi-turn.json`
- `failure-cases.json`

每个文件都映射到：

- [EvalCaseDataset.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalCaseDataset.java)

它的核心字段是：

- `datasetId`
- `version`
- `description`
- `cases`

### 3.2 单个 case 结构

每条 case 映射到：

- [EvalCaseDefinition.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalCaseDefinition.java)

核心字段包括：

- `caseId`
- `title`
- `category`
- `scenarioType`
- `agentId`
- `query`
- `history`
- `expectations`
- `tags`
- `notes`

这里最关键的两个字段是：

- `history`
- `expectations`

### 3.3 为什么 `history` 很重要

多轮评测不是把上下文手工拼进 query，
而是把前几轮 query 顺序重放。

每个历史轮次映射到：

- [EvalHistoryTurn.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalHistoryTurn.java)

这样做的好处是，
评测 runner 真的在复用主链已有的：

- `threadId`
- `MultiTurnContextManager`
- `multiTurnContext`
- `contextualizedQuery`

也就是说，
多轮评测测的不是“拼接后的文本效果”，
而是“系统当前真实的多轮机制”。

### 3.4 为什么 expectations 保持克制

预期结构映射到：

- [EvalExpectations.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalExpectations.java)

当前只放了规则可判的字段：

- `expectedIntent`
- `expectedTables`
- `expectedResultMode`
- `expectedSqlGenerated`
- `expectedSqlExecuted`
- `expectedSqlRetryCount`
- `expectedContextualizedQueryContains`

这是一个有意识的设计选择。

因为 V1 不想一开始就把复杂度抬到：

- 标准 SQL 对拍平台
- LLM-as-a-judge
- 人工标注平台

所以先把“能自动判的部分”做好。

---

## 4. Runner 是怎么执行的

### 4.1 入口是谁

真正的入口类是：

- [EvalRunner.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalRunner.java)

CLI 入口是：

- [LiteEvalCliApplication.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/LiteEvalCliApplication.java)

所以整条链路是：

```text
LiteEvalCliApplication
-> EvalRunner.runDefaultSuite()
-> 读取 datasets
-> 逐条 runCase(...)
-> 生成 report
-> 写出 json / md
```

### 4.2 为什么 runner 直接复用主链

这套评测没有额外造一个 fake executor。

它直接调用：

- [SearchLiteOrchestrator.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/SearchLiteOrchestrator.java)

这是非常关键的一个设计点。

因为这样测出来的就是：

- 当前真实 orchestrator
- 当前真实 graph / pipeline 逻辑
- 当前真实多轮上下文机制
- 当前真实 SQL / recall / result 行为

而不是一条专门为了评测“改造过”的旁路链路。

### 4.3 为什么要补 `runForEvaluation`

原本 orchestrator 只有：

- `stream(SearchLiteRequest request)`

它适合前端 SSE，
但不适合评测系统直接拿最终结构化状态。

所以这里加了：

- [SearchLiteRunResult.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/SearchLiteRunResult.java)
- `SearchLiteOrchestrator.runForEvaluation(...)`

它会额外回收：

- `threadId`
- `SearchLiteState`
- `List<SearchLiteMessage>`
- `durationMs`

这一步特别值，
因为评测系统就不用再从 SSE 文本里硬解析：

- `intentClassification`
- `recalledTables`
- `sql`
- `resultMode`
- `summary`

换句话说：

> 这一步把评测系统从“读日志评测”升级成了“读状态评测”。

### 4.4 一个 case 实际是怎么跑的

`EvalRunner.runCase(...)` 的执行顺序可以概括成：

```text
生成 threadId
-> 回放 history
-> 执行目标 query
-> 拿到 SearchLiteRunResult
-> 从 state / messages 抽字段
-> 对照 expectations 判定
-> 生成 EvalCaseResult
```

这里有两个重要细节。

#### 细节一：history 和目标 query 使用同一个 `threadId`

这保证了多轮上下文是真实生效的。

#### 细节二：文档召回结果不是从 state 取，而是从 messages 里取

因为当前 state 里有：

- `evidences`
- `documentText`

但没有直接存结构化的 `recalledDocuments` 列表。

所以 `EvalRunner` 通过遍历：

- `SearchLiteMessage`
- `stage == EVIDENCE`
- `payload.documents`

来补出：

- `recalledDocuments`

这也是一个很实用的折中实现：

- 不改主链状态对象
- 先把评测字段补齐

---

## 5. 结果结构是怎么组织的

### 5.1 单题结果

每条样例结果映射到：

- [EvalCaseResult.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalCaseResult.java)

它记录了三类信息。

第一类：主链运行结果

- `intentClassification`
- `recalledTables`
- `recalledDocuments`
- `recalledEvidences`
- `canonicalQuery`
- `contextualizedQuery`
- `sql`
- `sqlRetryCount`
- `resultMode`
- `rowCount`
- `summary`
- `error`
- `durationMs`

第二类：评测判断结果

- `intentMatched`
- `schemaRecallHit`
- `sqlGenerated`
- `sqlExecuted`
- `resultModeMatched`
- `multiTurnFollowupMatched`

第三类：收口信息

- `passed`
- `failedChecks`

这一层设计的好处是，
结果对象同时服务两件事：

- 机器可统计
- 人可阅读排障

### 5.2 总报告结构

总报告映射到：

- [EvalRunReport.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalRunReport.java)

它包含：

- `reportId`
- `generatedAt`
- `datasetFiles`
- `totalCases`
- `passedCases`
- `failedCases`
- `metrics`
- `results`

所以这份 JSON 报告本质上已经是一份完整的“评测快照”。

---

## 6. 指标是怎么计算的

指标汇总结构在：

- [EvalMetricsSummary.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalMetricsSummary.java)
- [EvalMetricValue.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalMetricValue.java)

每个指标都用同一个结构：

- `passed`
- `total`
- `rate`

### 6.1 统一计算思想

`EvalRunner.metric(...)` 的思路很简单：

1. 只统计“这个 case 配置了预期”的样例
2. `null` 不计入分母
3. `true` 计入通过

这意味着：

- 没定义预期的 case 不会污染指标
- 指标是可渐进扩展的

### 6.2 当前 6 个指标

当前支持：

- `intentAccuracy`
- `schemaRecallHitRate`
- `sqlGenerationRate`
- `sqlExecutionSuccessRate`
- `resultModeAccuracy`
- `multiTurnFollowupAccuracy`

这里有一个很值得注意的点：

`sqlGenerationRate` 和 `sqlExecutionSuccessRate` 目前不是“按 expectations 判”，
而是直接看真实运行结果：

- 是否生成 SQL
- 是否执行成功

这让它们更像系统健康指标。

而：

- `intentAccuracy`
- `schemaRecallHitRate`
- `resultModeAccuracy`
- `multiTurnFollowupAccuracy`

更像 case expectation 指标。

---

## 7. Markdown 报告是怎么生成的

Markdown 渲染器在：

- [EvalMarkdownReportRenderer.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalMarkdownReportRenderer.java)

它当前输出 4 块内容：

1. 报告头
2. 数据集列表
3. 指标表
4. 失败样例表
5. 全量 case summary

为什么 V1 的 Markdown 报告很重要？

因为 JSON 适合机器读，
但开发排障时真正高频打开的是 Markdown。

你可以一眼看到：

- 失败了多少题
- 失败集中在哪几类
- 每题失败检查项是什么
- 实际 `resultMode` / `error` 是什么

这让评测系统开始真正具备“工程反馈价值”。

---

## 8. 文件输出是怎么做的

输出逻辑在：

- [EvalReportWriter.java](D:/GitHub/DataAgent/data-agent-backend/src/main/java/com/alibaba/cloud/ai/dataagentbackend/lite/eval/EvalReportWriter.java)

每次运行会写四个文件：

- `latest-report.json`
- `latest-report.md`
- `report-时间戳.json`
- `report-时间戳.md`

这样做有两个直接好处：

### 8.1 `latest-*` 方便快速查看

你不用每次去找最新文件名。

### 8.2 时间戳归档方便版本对比

后续你可以直接比较：

- 改 prompt 前后
- 改 recall 前后
- 改多轮策略前后

这对后面写简历、做效果复盘都非常有帮助。

---

## 9. 为什么我说它“轻量但清晰”

这套系统没有上重型框架，
但它并不是随便拼起来的。

我认为它清晰的原因有 4 个。

### 9.1 数据结构和代码结构一一对应

dataset、case、expectations、result、report 都有单独类，
后续扩字段不会乱。

### 9.2 评测和主链职责清楚分开

评测系统：

- 不重构主链
- 不改业务流程
- 只负责执行、记录、统计、输出

主链：

- 继续负责真实推理和执行

### 9.3 规则判断优先

先把：

- intent
- recall
- sql 是否生成
- sql 是否执行
- result mode
- multi-turn context

这些低成本可判项做好。

### 9.4 保留扩展空间

当前实现虽然轻，但后面很容易继续往上加：

- 标准 SQL 对拍
- 结果集等价比对
- 人工标注位
- hallucination 标签
- LLM Judge

---

## 10. 这套系统暴露了哪些真实问题

最近一次真实环境跑出来之后，
这套评测系统已经清楚暴露出几类问题：

- fallback 场景容易被强行回答成 `success`
- schema recall 容易偏向 `users, orders`
- 多轮条件补充不稳定
- SQL grounding 不够强
- `resultMode=success` 不能等价理解为“答对”

这恰恰说明评测系统已经开始工作了。

如果一套评测系统永远只会产出“都很好”，
那它其实是没用的。

---

## 11. 当前实现的边界

虽然已经可用，但也要诚实记录它的边界。

### 11.1 还没有做结果集级别对拍

现在更多是在判：

- 是否召回了正确表
- 是否生成并执行了 SQL

还没有自动比较：

- 生成 SQL 的结果
- 标准 SQL 的结果

### 11.2 `resultMode` 还不是答案正确率

当前 `success` 更多表示：

- 链路跑通了
- SQL 执行了

而不是：

- 业务语义一定答对了

### 11.3 多轮判断仍然偏规则

现在的 `multiTurnFollowupMatched`
主要是通过：

- `contextualizedQuery` 是否包含预期片段

来判断。

这已经够做 V1，
但还不是最终版本。

### 11.4 真实环境跑批成本还不低

真实 LLM + recall + JDBC 执行时，
每题耗时已经比较明显。

这意味着后续如果题库扩大，
可能要再分：

- 快速回归集
- 标准评测集

---

## 12. 一句话总结

这套 Eval V1 的核心实现思想可以总结成一句话：

> 直接复用真实主链，用固定样例集把运行结果收敛成结构化记录、基础指标和可读报告。

它不是大而全的平台，
但已经是一套真正能帮助我们做效果验证、问题定位和版本对比的评测闭环。

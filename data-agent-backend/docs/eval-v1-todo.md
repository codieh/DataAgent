# Eval V1 开发清单

## E1. 定义样例数据格式

- 明确评测样例的 JSON 结构
- 至少支持：
  - `caseId`
  - `query`
  - `history`
  - `expectedIntent`
  - `expectedTables`
  - `expectedResultMode`
  - `notes`

交付物建议：

- `D:\GitHub\DataAgent\data-agent-backend\data\eval\schema\eval-case-schema.json`

---

## E2. 建立第一版样例集

- 从已有 `eval-question-bank.md` 中挑选并整理样例
- 先做小而精的一版，建议 15~30 条

建议覆盖：

- 单轮正常查询
- 多轮追问
- Schema 缺失
- SQL 为空
- SQL 执行失败 / fallback

交付物建议：

- `D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\single-turn.json`
- `D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\multi-turn.json`
- `D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\failure-cases.json`

---

## E3. 实现跑批入口

- 提供一个统一 runner
- 支持顺序执行样例
- 支持为每条样例生成独立 `threadId`
- 支持多轮历史注入

建议落点：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\java\com\alibaba\cloud\ai\dataagentbackend\lite\eval\EvalRunner.java`

---

## E4. 输出结构化结果

- 每条样例输出一份结构化结果
- 聚合成整体运行报告

每条记录建议包含：

- `caseId`
- `query`
- `history`
- `intentClassification`
- `recalledTables`
- `sql`
- `sqlRetryCount`
- `resultMode`
- `rowCount`
- `summary`
- `error`
- `durationMs`

输出位置建议：

- `D:\GitHub\DataAgent\data-agent-backend\data\eval-reports\latest-report.json`

---

## E5. 统计基础指标

第一版先统计：

- Intent 命中率
- Schema recall 命中率
- SQL 生成率
- SQL 执行成功率
- Result mode 命中率
- 多轮追问正确率

如果暂时无法自动判断“最终答案正确率”，可以先保留人工标注位。

---

## E6. 生成人类可读报告

- 在 JSON 之外，再产出一份 markdown 报告
- 报告应包含：
  - 总样例数
  - 成功数 / 失败数
  - 各类失败统计
  - 典型错误样例

建议输出：

- `D:\GitHub\DataAgent\data-agent-backend\data\eval-reports\latest-report.md`

---

## E7. 预留幻觉标注位

暂时不要求自动判别，但建议在结果结构里预留：

- `knowledgeHallucination`
- `reasoningHallucination`

便于后面升级为更完整的评测体系。

---

## E8. 验收清单

满足以下条件即可认为 Eval V1 可用：

- 样例可读取
- Runner 可执行
- 能产出 JSON 报告
- 能产出 Markdown 报告
- 能统计至少 5 个基础指标
- 能区分单轮 / 多轮 / 异常类样例

---

## E9. 开发边界提醒

本轮开发不要做：

- 不改 Graph 主链
- 不重做 SearchLite 主流程
- 不引入重型评测平台
- 不直接接 LLM-as-a-judge
- 不做大规模数据库平台化

重点是：

- 快速建立一套能支撑后续优化与简历表达的轻量评测闭环


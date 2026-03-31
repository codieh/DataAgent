# 📚 Document RAG 设计方案（V1）

## 1. 目标

本方案用于给 `data-agent-backend` 增加 **Document RAG** 能力，让系统除了 `schema` 和 `evidence` 之外，还能从本地业务文档中检索补充知识。

V1 目标不是做一个完整知识平台，而是做一个：

- 能接入本地文档
- 能切块、索引、召回
- 能进入当前 recall 体系
- 不破坏 SQL 主链路稳定性

---

## 2. 设计原则

### 2.1 先轻量，后增强

V1 不追求：

- 多租户知识管理
- 在线上传文档后台
- 复杂分块算法
- 重型向量数据库

V1 只追求：

- 本地文档可用
- 召回结果可观察
- 能作为现有 `evidence` 的补充

### 2.2 文档是“补充知识”，不是结构真相

在当前项目里：

- `schema`：硬约束，决定表、列、join、SQL 结构
- `evidence`：业务口径提示
- `document`：更长文本的背景知识 / 规则说明 / FAQ 补充

因此 V1 中：

- `document` **不直接主导 SQL 结构**
- `document` **先作为 evidence 的补充来源**

### 2.3 统一 recall 基础设施，不单独造轮子

Document RAG 应复用现有能力：

- `RecallDocument`
- `RecallService`
- `FileRecallDocumentStore`
- `KeywordRecallEngine`
- `VectorRecallEngine`
- `HybridRecallEngine`

只新增：

- 新的文档类型
- 文档读取与切块
- 文档索引初始化入口

---

## 3. 适用文档范围

V1 建议只支持以下类型：

- `md`
- `txt`
- `json`

原因：

- 实现简单
- 便于调试
- 文本结构清晰
- 足够支持指标定义、FAQ、业务规则说明等场景

V2 再考虑：

- `pdf`
- `docx`

---

## 4. 文档目录约定

建议新增本地文档目录：

- `D:\GitHub\DataAgent\data-agent-backend\data\documents`

可按主题继续细分子目录，例如：

- `data\documents\metrics`
- `data\documents\faq`
- `data\documents\business-rules`

这样后续更容易补 `topic/tags`。

---

## 5. 文档模型设计

### 5.1 新增类型

在 `RecallDocumentType` 中新增：

- `DOCUMENT`

### 5.2 文档切块后的 metadata

每个 chunk 至少保留以下 metadata：

- `sourceType=document`
- `docId`
- `docName`
- `sectionTitle`
- `chunkIndex`
- `topic`
- `tags`

推荐补充：

- `fileType`
- `relativePath`

### 5.3 RecallDocument 示例

```text
type = DOCUMENT
title = "销售指标定义 / GMV"
content = "GMV 指平台成交总额，默认按订单明细 quantity * unit_price 汇总，取消订单不计入。"
metadata = {
  sourceType: "document",
  docName: "metrics.md",
  sectionTitle: "GMV 定义",
  chunkIndex: 2,
  topic: "sales",
  tags: ["gmv", "sales", "metric"]
}
```

---

## 6. 切块策略

### 6.1 总体策略

V1 使用 **标题 + 段落优先** 的切块方式：

1. 先按标题切分 section
2. section 内按自然段聚合
3. 如果 section 太长，再按长度二次切块

### 6.2 为什么不用纯固定长度切块

纯固定长度虽然简单，但缺点明显：

- 语义边界可能被截断
- 标题与正文容易分离
- 召回结果解释性差

因此 V1 采用“结构优先、长度兜底”的方式。

### 6.3 chunk 大小建议

V1 建议每个 chunk 控制在：

- **200 ~ 500 个中文字符**

若超过上限，再继续切分。

### 6.4 overlap 策略

V1 暂不做复杂 overlap。

原因：

- 当前文档规模不大
- 先保证实现稳定
- 避免重复召回过多相邻 chunk

如果后续发现边界问题明显，再引入轻量 overlap。

---

## 7. 文档读取与切块流程

### 7.1 读取流程

对于每个文件：

1. 识别文件类型
2. 读取原始文本
3. 提取文档标题（优先文件名）
4. 解析为若干 section
5. 对 section 做 chunk
6. 转为 `RecallDocument(type=DOCUMENT)`

### 7.2 各文件类型建议

#### `md`

- 优先识别 `# / ## / ###` 标题
- 每个标题下的段落作为 section

#### `txt`

- 以空行分段
- 若存在明显标题行，可做轻量识别

#### `json`

- 若是结构化说明文档，可序列化成可读文本
- 不建议直接按原始 JSON 字符串大块索引

---

## 8. 索引初始化设计

### 8.1 新增初始化能力

建议新增：

- `POST /api/index/init/documents`

并将其接入：

- `POST /api/index/init/all`

### 8.2 初始化流程

```text
扫描 documents 目录
-> 读取文档
-> 切块
-> 生成 RecallDocument(DOCUMENT)
-> 生成 embedding
-> 写入本地持久化索引
```

### 8.3 索引文件

建议单独持久化：

- `D:\GitHub\DataAgent\data-agent-backend\data\recall\document-index.json`

不要和 evidence/schema 混写到一个文件里，便于调试和重建。

---

## 9. 召回策略设计

### 9.1 召回位置

建议放在当前 `evidence recall` 之后、`schema recall` 之前，或者与 evidence 并列。

当前推荐方式：

- **先把 document 作为 evidence 的补充来源**

也就是：

```text
query
-> evidence recall
-> document recall
-> 合并成业务上下文
-> schema recall
-> enhance / sql generate
```

### 9.2 topK 建议

V1 建议：

- `document recall topK = 2 ~ 3`

原因：

- 文档块通常较长
- 太多容易污染 prompt

### 9.3 使用方式

V1 中 document context 的定位：

- 提供业务背景
- 提供指标定义
- 提供规则说明
- 提供 FAQ 补充

V1 中不建议：

- 让 document 直接主导 SQL 表结构判断

---

## 10. 与 evidence 的关系

### 10.1 区别

`evidence` 更像：

- 精炼的规则项
- 短文本业务证据
- 口径提示

`document` 更像：

- 更长的背景知识
- 文档段落
- FAQ/说明材料

### 10.2 V1 的关系设计

建议：

- `evidence` 优先级高于 `document`
- `document` 作为 evidence 的补充

也就是：

```text
schema > evidence > document
```

其中：

- `schema` 决定结构
- `evidence` 决定口径
- `document` 决定背景语义补充

---

## 11. 与 hybrid recall 的关系

Document RAG 接入后，仍然走统一 recall 引擎：

- `keyword`
- `vector`
- `hybrid`

但建议对 `DOCUMENT` 设置独立权重，避免长文档块在 hybrid 中压过 schema/evidence。

后续建议新增配置：

- `search.lite.recall.weight.document`
- `search.lite.recall.topk.document`

---

## 12. 日志与可观测性

建议至少输出以下日志：

- 文档索引初始化数量
- 文档切块数量
- 每篇文档 chunk 数
- document recall topK 命中
- document 的 `keyword/vector/fused` 分数
- 命中的 `docName / sectionTitle / chunkIndex`

这样后续才能判断：

- 文档切块是否合理
- 召回是否命中了正确 section
- 文档是否在帮助系统，还是在制造噪声

---

## 13. 风险与控制

### 13.1 风险：文档噪声污染 SQL

控制方式：

- topK 控制在 2~3
- document 不直接主导 SQL
- prompt 中明确 document 是补充上下文

### 13.2 风险：长文档 chunk 太大导致命中不准

控制方式：

- 标题 + 段落切块
- 超长 section 再按长度切

### 13.3 风险：重复召回相邻内容

控制方式：

- V1 暂不做大 overlap
- 同文档命中过多块时可后续去重

### 13.4 风险：知识源边界不清

控制方式：

- 统一定义三类来源用途：
  - schema
  - evidence
  - document

---

## 14. 开发分步建议

### Step 5.1

- 新增 `RecallDocumentType.DOCUMENT`
- 定义 `document-index.json`

### Step 5.2

- 实现文档读取器
- 实现 Markdown / txt / json 的基础切块

### Step 5.3

- 增加 document 索引初始化
- 接入 `/api/index/init/documents`
- 接入 `/api/index/init/all`

### Step 5.4

- 实现 document recall
- 将结果作为 evidence 的补充上下文接入主链路

### Step 5.5

- 增加日志与调试信息
- 观察命中文档块是否合理

---

## 15. V1 完成标准

Document RAG V1 完成时，至少应满足：

- 能读取本地文档目录
- 能按标题/段落切块
- 能生成 `DOCUMENT` 类型 recall 文档
- 能建立本地持久化索引
- 能通过统一 recall 机制召回文档块
- 能进入主链路作为 evidence 补充
- 日志可观察、结果可调试

---

## 16. 后续演进方向（V2+）

后续可以考虑：

- `pdf/docx` 支持
- 更细粒度 chunk overlap
- 更细 metadata 过滤
- 文档类型分层（FAQ / 指标定义 / 业务规则）
- 基于 PostgreSQL / pgvector 的持久化
- 文档召回独立评测

---

## 17. 结论

对于当前 `data-agent-backend`，Document RAG 最适合的落地方式是：

- **统一进现有 recall 基础设施**
- **轻量实现本地文档索引**
- **先作为 evidence 的补充，而不是替代 schema**

这条路线：

- 成本可控
- 风险较低
- 容易讲清楚
- 非常适合作为简历项目的下一阶段增强

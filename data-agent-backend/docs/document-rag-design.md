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

## 18.1 pgvector 接入现状（记录时间：2026-04-29）

当前 lite-backend 已新增 `pgvector` 向量检索实现，并且默认 recall provider 已继续升级到：

- `bm25-pgvector-rerank`

实现方式保持和当前 recall 主结构一致的分层思路：

- 文档索引仍由 `RecallDocumentStore` 负责本地 JSON 持久化
- 向量检索层新增：
  - `PgVectorProperties`
  - `PgVectorSearchService`
- `HybridRecallEngine` 现在支持：
  - `pgvector`
  - `hybrid-pgvector`
  - `bm25-pgvector-rerank`

也就是说，这次切换的重点是：

- **把向量库统一收敛到 pgvector**
- **不改 RecallDocument / RecallService / KeywordRecallEngine 的主结构**

### 当前 pgvector 的工作方式

1. `RecallEmbeddingService` 先为 `RecallDocument` 补 embedding
2. `PgVectorSearchService` 在查询时可选同步文档到 PostgreSQL
3. 使用 `embedding <=> queryVector` 做余弦距离检索
4. `HybridRecallEngine` 先把：
   - BM25 召回
   - pgvector 召回
   做候选融合
5. 再通过 lightweight reranker 做最终排序收敛

### 当前边界

- 如果 pgvector 不可用，会自动回退到本地 `VectorRecallEngine`
- 当前主业务 SQL 数据源依旧是 MySQL
- pgvector 只用于 recall 向量检索，不用于业务查询

### 18.1.1 推荐的本地运行方式

如果要在本地真正启用 pgvector，建议准备一套独立 PostgreSQL 实例，并安装 `pgvector` 扩展。

当前配置项在：

- `D:\GitHub\DataAgent\data-agent-backend\src\main\resources\application.yml`

关键环境变量：

- `RECALL_PGVECTOR_ENABLED`
- `RECALL_PGVECTOR_URL`
- `RECALL_PGVECTOR_USERNAME`
- `RECALL_PGVECTOR_PASSWORD`
- `RECALL_PGVECTOR_TABLE`
- `RECALL_PGVECTOR_DIMENSIONS`

默认配置思路是：

- URL：
  - `jdbc:postgresql://127.0.0.1:5432/data_agent_recall`
- 表名：
  - `recall_vectors`
- 维度：
  - `1024`

### 18.1.2 当前迁移策略为什么是“渐进式”

这次没有直接把整个 recall 系统彻底改成 PostgreSQL-only，而是采用了渐进式迁移：

- `RecallDocumentStore`
  - 继续负责本地 JSON 持久化
- `PgVectorSearchService`
  - 负责向量检索
- `HybridRecallEngine`
  - 继续负责关键词 + 向量融合

这样做的好处是：

- 主链业务代码改动小
- 即使 pgvector 临时不可用，也不至于让 recall 整体失效

所以这次接入更准确的定位是：

> **把向量检索后端统一收敛到 pgvector，而不是一次性重写整个 recall 基础设施。**
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

---

## 18.2 BM25 + pgvector + reranker（记录时间：2026-05-04）

当前 recall 已开始按三段式实现：

1. **BM25**
   - 强化表名、列名、指标词、业务术语等 lexical 命中
2. **pgvector**
   - 负责 dense semantic recall
3. **reranker**
   - 在融合候选后做 query-aware 最终排序收敛

当前这版 reranker 还是轻量实现：

- 不是额外的 cross-encoder 服务
- 而是先基于 query token 覆盖率、标题/表列精确命中、融合分数做最终重排

这一步的价值是先把 recall 清晰拆成：

- lexical
- semantic
- final ranking

后面如果评测证明值得升级，再继续替换成更强的模型型 reranker。

---

## 18. BM25 与 `bge-m3` 的理论补充（记录时间：2026-05-04）

当前项目使用本地 embedding 模型：

- `bge-m3`
- `http://localhost:11434/v1/embeddings`

虽然当前代码里的 hybrid recall 仍是“关键词 + 向量分数融合”的轻量实现，但如果要进一步判断：

- 为什么 `BM25 + vector` 往往比“简易关键词命中 + vector”更稳
- 为什么不能把 `bge-m3` 简单理解成“一个向量模型就能替代全部 recall”

就需要先补一点检索理论背景。

### 18.1 BM25 是什么

BM25 可以理解为：

> **在传统词项检索里，对“这个词在本文里出现得够不够多、够不够稀有、文档会不会太长”做综合平衡的一种排序函数。**

它不是 embedding，也不依赖语义空间，而是典型的 lexical retrieval。

BM25 最常见的打分形式可以写成：

```text
score(D, Q) = Σ IDF(qi) * ( tf(qi, D) * (k1 + 1) )
                         / ( tf(qi, D) + k1 * (1 - b + b * |D| / avgdl) )
```

其中：

- `D`
  - 文档
- `Q`
  - 查询
- `qi`
  - 查询里的某个词项
- `tf(qi, D)`
  - 词项 `qi` 在文档 `D` 中出现的次数
- `|D|`
  - 文档长度
- `avgdl`
  - 语料平均文档长度
- `IDF(qi)`
  - 逆文档频率，衡量这个词是否稀有
- `k1`
  - 控制词频饱和速度
- `b`
  - 控制文档长度归一化强度

### 18.2 BM25 的三个核心思想

#### 1）词频有用，但收益递减

一个词在文档里出现 3 次，通常比出现 1 次更相关；
但出现 30 次未必比 3 次强很多。

BM25 用 `k1` 控制这种“边际收益递减”，避免高频词把分数无限拉高。

#### 2）稀有词更有区分力

如果一个词在几乎所有文档里都出现，那它对排序帮助很小；
如果一个词只出现在很少数文档里，它往往更能区分相关性。

这就是 `IDF` 的作用。

在当前项目场景里，像下面这些词通常就更像高价值词项：

- 指标缩写：`GMV`
- 表名：`order_items`
- 列名：`unit_price`
- 业务短语：`高消费用户`

#### 3）长文档不能天然占便宜

长文本因为包含词更多，天然更容易“碰巧命中” query。

BM25 用文档长度归一化削弱这种偏差，避免长 chunk 因为字多而虚高。

### 18.3 BM25 为什么比当前简易 `KeywordRecallEngine` 更强

当前 lite backend 的关键词召回本质上是：

- token 命中 title：加较高分
- token 命中 content：加较低分
- 最后累加排序

它的优点是简单、好调试，但和 BM25 相比，少了三类关键能力：

- **没有 IDF**
  - 分不清“高价值稀有词”和“普通常见词”
- **没有词频饱和**
  - 重复出现的词容易被简单累加放大
- **没有长度归一化**
  - 长文档 chunk 更容易天然得高分

所以在以下场景中，BM25 通常会更稳：

- schema 表名/列名精确召回
- FAQ / evidence 中的规则短语检索
- query 很短，但关键词特别强
- 文档 chunk 很多，需要控制长文本偏置

### 18.4 BM25 的边界

BM25 强在词面，不强在语义。

它不擅长：

- 同义改写
- 自然语言绕写
- 跨语言匹配
- “字面不重合但语义相近”的问题

例如：

- query：`高价值客户`
- 文档只写：`核心用户`

如果没有共享词项，BM25 很可能召不出来，或者排序靠后。

这也是为什么 RAG 里常见的是：

> **BM25 负责 lexical precision，vector retrieval 负责 semantic recall。**

### 18.5 `bge-m3` 是什么

`bge-m3` 可以理解为一个面向检索任务的统一表示模型，名称里的 `M3` 常被概括为：

- **Multi-Function**
- **Multi-Lingual**
- **Multi-Granularity**

它的重要特点不是“只有一个 dense embedding 很强”，而是：

> **同一个模型家族，既考虑 dense retrieval，也考虑 sparse retrieval，还考虑 multi-vector retrieval。**

从检索系统视角看，它提供的不是单一能力，而是一种“统一检索表示”的思路。

### 18.6 `bge-m3` 的架构直觉

从工程理解上，可以把 `bge-m3` 的能力拆成三层：

#### 1）Dense representation

把 query / document 编码成一个稠密向量。

优点：

- 适合语义相似
- 对改写、同义表达更稳
- 适合一般性自然语言问题

这也是当前项目现在真正接入并使用的部分：

- `RecallEmbeddingService`
- `VectorRecallEngine`
- `PgVectorSearchService`

#### 2）Sparse / lexical-aware representation

`bge-m3` 并不只会给出 dense 向量，它的设计目标之一就是让模型保留 lexical 信号，
即：

- 哪些 token 很关键
- 哪些词项需要更大权重

这一层能力的目标，不是完全复制 BM25，
而是让模型学到“更智能的稀疏检索信号”。

#### 3）Multi-vector representation

单向量会把整段文本压缩成一个向量，信息密度有限；
多向量表示则允许 query 与 document 在更细粒度上匹配。

它更适合：

- 长文本
- 多约束 query
- 局部证据匹配

这对 document RAG 很重要，因为一个 chunk 里常常混有：

- 定义
- 例外条件
- 公式
- 补充说明

如果只用单向量，容易把这些局部信号压平。

### 18.7 为什么不能把 `bge-m3` 直接等同于当前 `keywordRecall`

这是之前留下的一个关键 TODO，这里直接给出结论：

> **不能把 `bge-m3` 直接当成当前 `KeywordRecallEngine` 的无缝替代品，因为两者优化目标和输出形式并不一样。**

原因主要有四个：

#### 1）当前接入方式只暴露了 dense embedding

当前项目里调用的是：

- `/v1/embeddings`

这条链路拿到的是 dense vector，不是 `bge-m3` 的完整 sparse / multi-vector 检索信号。

所以当前代码实际上只用了它的 dense 能力，并没有真正把它当成“统一 hybrid 检索模型”来用。

#### 2）keyword recall 需要倒排式词项可解释性

当前 `KeywordRecallEngine` 的行为非常直接：

- 哪个 token 命中
- 命中了 title 还是 content
- 为什么这个文档排前面

都很容易解释。

而 dense embedding 的分数是语义相似度，不天然具备：

- token 级命中可解释性
- 稀有词精确控制
- 表名列名这类结构词的硬匹配偏好

#### 3）schema recall 特别依赖精确词面命中

在当前项目里：

- `SCHEMA_TABLE`
- `SCHEMA_COLUMN`

很多时候要求的不是“语义差不多”，而是：

- 表名尽量准
- 列名尽量准
- 业务短语和字段别名尽量准

这类任务天然更需要 BM25 / sparse / exact match 一侧的能力。

#### 4）模型能力和系统能力不是一回事

即使 `bge-m3` 模型本身支持更丰富的检索表示，
系统如果没有把这些表示以：

- sparse field
- multi-vector field
- hybrid ranker

的形式真正接进索引和搜索引擎，
那么它在工程上仍然只是“一个 dense embedding 模型”。

### 18.8 为什么 `bge-m3` 仍然对当前 Recall 很重要

### 18.1 启发一：不要把 keyword recall 和 vector recall 完全割裂

`bge-m3` 的价值不只是 dense embedding，本质启发是：

- 词面命中有价值
- 语义相似也有价值
- 检索系统应该同时利用这两类信号

这说明当前项目继续保留并强化 `hybrid recall` 是正确方向，而不是简单切换到“只做向量检索”。

对应到当前项目：

- `schema recall` 需要保留表名、列名的精确命中能力
- `evidence recall` 需要保留术语、规则短语的关键词能力
- `document recall` 需要利用语义召回补齐同义表达和自然语言问法

### 18.9 启发二：metadata 与 chunk 质量会直接决定 hybrid 是否有效

`bge-m3` 可以提供更强的语义检索能力，但前提仍然是：

- 文档切块合理
- `topic/tags/docType` 元数据准确
- 不同知识源边界清楚

否则即使 embedding 模型很强，也会出现：

- 命中语义相似但业务不相关的 chunk
- 文档噪声压过 evidence/schema
- query 稍模糊时召回范围过宽

因此当前项目后续仍应优先优化：

- chunk 粒度
- metadata 质量
- source/type 边界

### 18.10 启发三：更适合采用“先筛后排”的检索链路

基于 `bge-m3` 的特点，当前项目的 recall 更适合继续演进为：

1. **先筛**
   - 先用 `type/topic/tags/docType` 等 metadata 缩小候选集
   - 或先做轻量 keyword/topic 粗筛
2. **再排**
   - 再用 vector / hybrid 对候选集排序
3. **必要时再做 rerank**
   - 对 topN 结果进一步做规则加权或二次排序

这比当前“一次 search 直接决定最终 topK”更稳，也更符合多知识源 recall 的实际需求。

### 18.11 启发四：不同知识源应该有不同的融合策略

即使都使用 `bge-m3` 做 embedding，以下几类知识也不应完全等权：

- `SCHEMA_TABLE`
- `SCHEMA_COLUMN`
- `EVIDENCE`
- `DOCUMENT`

后续更合理的策略应该是：

- `schema`：保留较强关键词权重，强调精确结构命中
- `evidence`：强调规则短语、术语和 topic 一致性
- `document`：强调语义补充能力，但避免喧宾夺主

也就是说，模型可以统一，但召回策略不能统一为“一套简单权重打天下”。

### 18.12 对当前代码的直接落地建议

基于 `bge-m3` 的启发，后续代码层最值得做的不是“换模型”，而是以下演进：

- **先筛后排**
  - metadata/topic 过滤后再做 hybrid recall
- **扩大候选，再精排**
  - 先取较大的候选集，再做二次排序，而不是一次 topK 截断
- **分来源配置权重**
  - `schema/evidence/document` 使用不同融合权重
- **增加 rerank 思维**
  - 对定义类、规则类、FAQ 类文档做不同后处理
- **提高日志可解释性**
  - 明确区分：
    - keyword score
    - vector score
    - metadata filter 命中
    - rerank/fused score

### 18.13 对当前项目的最终理论结论

结合 BM25 和 `bge-m3`，当前项目可以得出一个比较明确的理论判断：

- **BM25**
  - 负责词面精确命中
  - 适合 schema / 术语 / 规则短语
- **Dense vector**
  - 负责语义召回
  - 适合定义改写、自然语言问法、背景说明
- **`bge-m3`**
  - 提醒我们不要把检索能力只理解成“单向量相似度”
  - 更合理的方向是统一 dense / sparse / 多粒度检索思路

所以当前 backend lite 后续最合理的 recall 演进方向不是：

- 只加强关键词命中
- 或只更换 embedding 模型

而是：

> **在 metadata 粗筛的基础上，用更正规的 sparse/BM25 能力补强 lexical recall，再与 dense retrieval 结合，并逐步引入更细粒度的排序策略。**

### 18.14 一句话总结

`bge-m3` 对当前项目最大的启发不是“模型更强”，而是：

> **当前 recall 应继续朝“metadata 粗筛 + hybrid 排序 + 多知识源分类型治理”演进。**

这条路线既符合当前项目的工程现状，也更容易在后续评测与简历表达中讲清楚。

---

## 19. 多知识源使用策略（记录时间：2026-04-06）

在参考 `management` 项目之后，当前 backend 的下一阶段重点不再只是“多召回一些内容”，
而是要把不同知识源真正**按角色使用**。

### 19.1 设计目标

当前知识使用策略调整为：

- `schema`
  - 结构真相、硬约束
- `evidence`
  - 业务规则、FAQ、指标提示
- `document`
  - 定义、背景说明、术语解释

这意味着后续 prompt 不再把 `evidence` 和 `document` 简单拼接成一个大字符串，
而是明确告诉模型：

- 什么能决定 SQL 结构
- 什么能补充业务规则
- 什么能解释业务概念

### 19.2 为什么要这样做

此前已经暴露出一个典型问题：

- query：`高消费用户`
- evidence：命中 `核心用户定义`
- document：命中 `高消费用户定义`

如果把这些信息混在一起，模型很容易：

- 召回对了 document
- 但仍被不匹配的 evidence 抢走主语义

所以这一阶段的核心优化方向不是“再召回更多”，而是：

> **让 query 更有机会使用到真正匹配的定义型知识。**

### 19.3 当前实现方向

当前 backend 已开始向 `management` 的思路靠拢：

- `EvidenceFileStep`
  - 不再把 evidence 与 document 直接合并
  - 而是分别格式化为：
    - 业务规则与 FAQ 提示
    - 定义与背景文档
- `EnhanceMinimaxStep`
  - 在 query rewrite / query enhance 时引入：
    - 业务规则
    - 定义文档
  - 但要求：
    - 只能用于澄清术语
    - 不能引入新的业务要求
- `SqlGenerateMinimaxStep`
  - prompt 中显式区分：
    - schema
    - evidence
    - documents
  - 并强调：
    - schema 决定结构
    - evidence 决定规则提示
    - document 提供定义解释

### 19.4 后续继续优化的重点

后续还可以继续增强：

- 判断某条 evidence 是否与 query 语义匹配
- 对“定义型 document”做更强优先级提示
- 对不匹配的 evidence 做降权或抑制
- 把定义型知识进一步转化为：
  - topN / 阈值 / 默认周期
  这类更强的 SQL 约束

### 19.5 一句话总结

当前多知识源使用策略的方向是：

> **不是把 schema/evidence/document 一起塞给模型，而是让它们以不同角色参与决策。**

# 智能销售数据分析 Agent：核心面试题库

> 这不是“把所有可能问题都背一遍”的题库，而是根据两场真实面试筛出的核心追问。
> 目标是让回答能够落到代码、数据结构、设计取舍和证据，而不是只说技术名词。
>
> 更细的 180 道参考题见 [interview-question-bank-extended.md](./interview-question-bank-extended.md)；
> 两场面试的逐题复盘见
> [15-interview-retrospective.md](../../docs/tutorial/15-interview-retrospective.md)。

## 使用方法

每道题都按下面五步回答：

1. **结论**：第一句话直接回答问题。
2. **实现**：说出真实对象、数据结构或执行顺序。
3. **理由**：解释为什么这样设计。
4. **边界**：主动说明没有实现什么、哪里仍有风险。
5. **证据**：给出代码、实验、日志或评测结果。

不要逐字背诵。闭卷时只要能完整覆盖这五项即可。

---

## A 级：任何一场项目面都必须答对

### 1. 请用 90 秒介绍项目

这是一个面向电商销售数据的自然语言分析 Agent。用户可以询问销售额、订单趋势、
商品表现、用户消费和库存情况，后端会让模型按需调用表结构检索、业务知识检索、
SQL 查询、历史结果读取和 Python 分析等工具。

流程上，FastAPI 先创建会话消息和一次 Run，后台任务再进入 LangGraph。图先做输入
安全检查，然后在 `agent_decide → tools → agent_decide` 之间执行 ReAct 式循环。
SQL 工具只提交候选 SQL，真正执行前必须经过 SQLGlot AST 校验和可选人工审核。
查询结果完整保存为 CSV，SQLite 保存业务状态和结果预览，复杂统计可以在受限 Docker
容器中执行 Python。REST 用于读取稳定快照，SSE 用于实时推送执行过程。

我重点解决的是三类问题：模型不了解数据库导致选错表和编造字段；长会话和大结果集
挤占模型上下文；模型生成的 SQL 和 Python 代码不能直接信任。当前长期记忆自动抽取
和完整 Python 版离线评测还没有接入，面试时不会把它们说成已经量化验证的能力。

代码入口：

- `app/application/run_commands.py`
- `app/application/executor.py`
- `app/workflow/graph.py`
- `app/workflow/nodes/analysis.py`

### 2. 为什么把 Java 工作流版本重构成 Python + LangGraph？

重构不是因为 Python 天然比 Java 更好，而是需求从“固定阶段依次执行”变成了“模型根据
中间结果决定下一步”。固定工作流适合路径稳定的查询，但复杂问题可能需要再次查表、
补充 SQL、读取历史结果或做 Python 统计，步骤数无法预先完全确定。

Python 版本把这些能力封装成工具，让模型在有预算和安全边界的循环里按需选择；SQL
校验、人工审核、执行和最终结果整理仍然保留为确定性节点。这样不是把整个系统交给
模型，而是把不确定的探索放进 Agent Loop，把安全和生命周期放在工作流里。

必须主动说明：当前还没有完成 Java 工作流版与 Python ReAct 版的同数据集对照评测，
所以只能说“改变了可支持的任务形态”，不能声称“准确率已经提升”。

### 3. 当前 LangGraph 一共有几个节点，怎么流转？

当前有 7 个业务节点：

1. `input_guard`：输入注入检查。
2. `agent_decide`：调用 LLM 决定工具或结束。
3. `tools`：执行模型选择的工具。
4. `sql_validate`：SQLGlot AST 安全校验。
5. `human_feedback`：可选人工审核中断。
6. `sql_execute`：执行只读 SQL 并保存数据集。
7. `result`：整理全部结果并生成最终输出。

主循环是：

```text
START → input_guard → agent_decide
                         ↓ tool call
                       tools
                         ↓
            agent_decide / sql_validate / result

sql_validate → human_feedback? → sql_execute → agent_decide
agent_decide 无工具调用 → result → END
```

不能把 `START`、`END` 说成业务节点，也不能把概念图中的“规划、召回、生成 SQL”误说成
真实独立节点。事实来源是 `app/workflow/graph.py:35-75`。

### 4. LangGraph 的图是怎样执行的？并行节点怎样合并 State？

LangGraph 按 Pregel 的 superstep 推进。一个 superstep 开始时，同层节点读取相同的
已提交 State；它们执行完成后在屏障处统一提交状态增量，下一步才能看到新状态。

本项目只有 `messages` 字段通过
`Annotated[list[AnyMessage], add_messages]` 配置了 reducer。普通字段在先后两个
superstep 中由后值替换前值；如果未来两个并行节点在同一 superstep 同时写一个没有
reducer 的字段，不是“最后完成者覆盖”，而是会抛 `InvalidUpdateError`。

当前业务图没有 fan-out 并行分支，所以主要表现为串行更新。但使用 LangGraph 作为核心
技术，就必须理解它的一般并发语义，而不能只回答“我的图是串行的”。

代码依据：`app/workflow/state.py:19` 和 `app/workflow/graph.py`。

### 5. `AnalysisState`、checkpoint 和 SQLite 业务表分别保存什么？

三者服务不同层次：

- `AnalysisState` 是一次 Run 的工作内存，保存消息、Schema、知识、SQL、观察、结果引用
  和预算计数，由节点读取并返回增量。
- checkpoint 保存 LangGraph 的状态快照和执行位置，用于 `interrupt` 后恢复，不适合
  前端业务查询。
- SQLite 业务表保存会话、消息、Run、阶段、事件、工具调用、审核、结果引用等稳定事实，
  用于历史页面、审计、重试和 API 查询。

当前使用 `run_id` 作为 LangGraph `thread_id`，所以 checkpoint 隔离的是一次运行；
跨轮会话连续性来自 SQLite 消息和摘要，而不是直接复用上一次图状态。

### 6. `conversation_id`、`run_id` 和 `thread_id` 有什么区别？

`conversation_id` 表示用户看到的一段会话，一段会话可以有多轮提问。`run_id` 表示其中
一次分析任务。当前实现把 `run_id` 同时传给 LangGraph 作为 `thread_id`。

这样做可以避免同一会话中的并发提问、重试和人工审核互相覆盖 checkpoint。代价是每次
Run 都要从 SQLite 重新构造会话上下文，不能直接继承上一 Run 的临时工具状态。

### 7. SQLite 里有哪些核心表？一行分别表示什么？

不要回答“就是一张消息表”。最少要说清下面七张：

| 表 | 一行表示什么 | 关键关联 |
|---|---|---|
| `conversations` | 一段用户会话 | 主键 `id` |
| `messages` | 会话中的一条 user/assistant/system 消息 | `conversation_id` |
| `analysis_runs` | 一次问题分析任务 | `conversation_id` |
| `stage_runs` | 某个 Run 中一个阶段的一次执行 | `run_id` |
| `tool_calls` | Agent 发起的一次工具调用 | `run_id` + `sequence` |
| `run_events` | 一条可重放的运行事件 | `run_id` + 递增 `seq` |
| `result_sets` | 一次查询结果的预览和文件引用 | `run_id` |

另外还有 `queries`、`artifacts`、`review_checkpoints`、核心记忆和摘要状态等表。数据库
模型位于 `app/infrastructure/persistence/models.py`。

### 8. 从源文档到 RAG 返回结果，完整计算过程是什么？

离线阶段先读取 TXT/Markdown，按标题和自然段切分。普通段落保持完整，超长语义单元按
句子等分隔符继续切，目标上限为 512 Token，超长切分使用 64 Token overlap。文档哈希
和 chunk 记录保存在 manifest，内容变化才更新 Chroma 并删除失效 chunk。

查询阶段有两个召回分支：

- BM25：匹配字段名、表名和业务关键词。
- Chroma 向量召回：用余弦距离计算，代码转换为 `similarity = 1 - distance`，低于
  0.25 的候选过滤。

两个分支先各取最终 TopK 的 4 倍候选，再用 RRF：

```text
RRF(d) = Σ 1 / (10 + rank_i(d))
```

业务知识最终 Top5；Schema 初始 Top4，再沿外键补充直接关联表，总数最多 8。当前没有
Cross-Encoder 或 LLM reranker，简历应写“RRF 融合排序”，不能写成独立重排模型。

### 9. 为什么 Schema 召回后还要扩展外键邻居？

用户问“购买过手机的用户”时，语义上容易命中 `users` 和 `products`，但真实 Join 还
需要 `orders`、`order_items`。纯语义相似度不保证连接路径完整，因此代码从命中表沿
外键关系补充直接邻居。

当前只做一跳扩展，可能带入噪声，也可能无法覆盖更长路径。更成熟的演进方向是把 Schema
建成图，在语义命中表之间求最小连接子图，而不是无限增加 TopK。

### 10. 多轮上下文什么时候压缩？Agent 循环里的工具结果怎么办？

这里有两套不同机制，不能混在一起：

- **跨轮会话压缩**：一次 Run 开始构建历史上下文时，摘要 Token 加未摘要消息 Token
  达到 `65536 × 0.8` 后触发滚动摘要，保留最近约 30% 原文，并用摘要游标避免重复归档。
- **单次 Run 内压缩**：每轮 `agent_decide` 前投影工具消息。Schema 工具结果只保留表名
  和状态引用；SQL 全量结果不直接放 ToolMessage，而是保存成数据集，只给模型结果编号、
  行数和有限预览，需要时再调用历史结果工具读取。

因此，面试官指出“工具结果会在 Agent Loop 内增长”是正确风险，但当前不是只靠会话摘要
解决，而是用结果引用和 ToolMessage 投影单独控制。

### 11. 项目中的“长期记忆”到底实现到什么程度？

默认在线生效的是：

- 用户明确要求记住时，`rewrite_core_memory` 整块改写核心记忆。
- 同一会话的近期原文和滚动摘要。
- 历史消息和历史结果查询工具。

没有完整接入的是：

- `memory_backend` 默认是 `none`。
- `LongTermMemoryExtractor` 已实现并实例化，但主链没有调用。
- `ContextBuilder` 当前返回空的 `longTermMemories`。
- 记忆 TTL 淘汰函数已有实现，但没有主链调用。

所以简历当前应写“近期消息、滚动摘要、核心记忆和历史检索”，不能写成“每轮自动抽取并
向量召回用户长期记忆”。

### 12. 为什么用 SQL 后还需要 Python 分析？

SQL 更适合把过滤、关联、聚合下推到数据库；Python 用于数据库 SQL 不方便表达的统计和
数据框操作，例如异常检测、相关性、多结果集合并和图表数据准备。不是因为“结果一大就
必须用 Python”，也不能把本项目说成处理海量数据的平台。

当前单次分析最多读取 5 万行。模型生成 Python 后，后端先用 Python AST 做导入和危险
调用检查，再在一次性 Docker 容器里执行。输入 CSV 只读挂载，输出目录可写。

### 13. Docker 是怎么调用的？有没有隔离？

后端不是使用 Docker SDK，而是通过 `asyncio.create_subprocess_exec` 调用 `docker run`。
“用命令行启动”不等于“没有隔离”。实际容器启用了：

- `--network none`
- `--read-only`
- `--cap-drop ALL`
- `no-new-privileges`
- 非 root 用户 `65534:65534`
- CPU、内存、PID 和执行超时限制
- 代码与输入只读挂载，只有输出目录可写

静态 AST 检查和容器隔离是两层防御：前者尽早拒绝明显危险代码，后者限制漏网代码的运行
权限。实现位于 `app/analysis/sandbox.py` 和 `app/analysis/service.py`。

### 14. Python 重构后效果提升了吗？怎么证明？

当前没有完成 Python 版本的正式离线评测，因此正确回答是：

> Python 版本已经验证了多步工具调用、SQL 安全、结果持久化和沙箱执行等功能链路，
> 但还没有用同一评测集和 Java 工作流版做量化对照。所以目前只能说明它支持更动态的
> 探索路径，不能声称准确率已经提升。下一步会固定模型、数据、提示词和并发，比较任务
> 完成率、结果正确率、工具路径、安全拦截、延迟和 Token 成本。

任何没有实验数据支撑的“更准确”“更稳定”都不要说。

---

## B 级：核心机制追问

### 15. 这是 ReAct 还是固定工作流？为什么最后还有 `result` 节点？

它是“Agent 工具循环 + 确定性工作流”的混合架构。模型在
`agent_decide ↔ tools` 中决定检索和分析步骤；SQL 校验、审核、执行以及最终输出格式
由固定节点控制。

`result` 节点的职责是展示层收尾，不是替代前面的探索：Agent 可以先执行多条 SQL、读取
历史结果或做 Python 分析，收集足够证据后再结束，`result` 把已有证据整理成统一的文字、
指标和图表结构。当前最终节点只读取有限结果预览，因此大结果必须先由 SQL 聚合或 Python
计算，不能从样本行推断全量结论。

### 16. 为什么没有独立意图识别节点？

普通对话、数据查询、历史结果和记忆操作都由原生 Tool Calling 决定，减少一次固定 LLM
调用，也避免分类错误把后续路径锁死。输入注入仍由确定性 `input_guard` 提前拦截。

这不是说意图识别没有价值。当业务路由、权限或模型选择必须在调用主模型前确定时，应增加
独立分类器；当前单体场景暂时没有这个必要。是否有效仍需用安全与路由评测验证，不能只凭
“简单测试看起来能分清”。

### 17. 工具怎样注册？`execute_sql` 为什么不直接执行？

工具通过 LangChain `@tool` 定义，再转换成 OpenAI 原生 Function Calling Schema。
模型只能选择工具和填写公开参数，`InjectedState` 等运行态由后端注入。

`execute_sql` 只把候选 SQL 写入 State 并设置 `pending_sql_validation`。图随后必须进入
`sql_validate`，通过 AST 校验和可选审核后，才由 `sql_execute` 访问数据库。这样模型
不能通过一次 Tool Calling 绕过安全边界。

### 18. SQL 安全具体做了什么？

`inspect_select_sql` 使用 SQLGlot 解析 AST，主要检查：

- 只允许单条 SELECT。
- 禁止系统库、危险函数、变量和导出语句。
- 表与字段必须在召回 Schema 白名单中。
- 禁止 `SELECT *`。
- Join 必须有 `ON/USING`，显式 `CROSS JOIN` 除外。
- 敏感字段不能返回明细，但允许部分聚合。
- 缺少 LIMIT 或 LIMIT 过大时统一收紧。

执行层还有只读 Session、查询超时和结果行数上限。AST 解决结构识别，不等于权限控制，
生产环境仍应使用只有 SELECT 权限的数据库账号。

### 19. 人工审核怎样中断和恢复？

SQL 校验通过后，如果开启审核，`human_feedback` 调用 LangGraph `interrupt`。当前 State
和执行位置写入 SQLite checkpoint，业务库把 Run 标记为 `waiting_review` 并保存审核记录。

用户审批后，后端使用同一个 `run_id/thread_id` 调用
`Command(resume={"approved": ..., "comment": ...})`。图从中断点恢复，不从头重新调用
模型。checkpoint 是运行时恢复数据，审核记录是业务事实，两者不能混为一张表。

### 20. 取消任务到底取消了什么？

取消不是只把数据库状态改成 `cancelled`。控制服务先写入取消终态和事件，再通过
`TaskRegistry.cancel_and_wait` 对后台 `asyncio.Task` 调用 `cancel()`，向执行协程注入
`CancelledError`，使 `graph.astream` 停止。

执行器在完成和失败路径还会再次检查 Run 是否已取消，避免晚到的完成事件覆盖取消状态。
局限是某些已经进入底层阻塞调用的操作未必能瞬间停止，因此数据库超时、LLM 超时和 Docker
超时仍然必要。

### 21. 项目里的请求都是同一个线程串行执行吗？

不是。FastAPI 路由和 LangGraph 主流程主要运行在事件循环线程，等待网络和异步数据库时
会让出执行权，不是一直占用线程。同步的 MySQL、Chroma/BM25、文件操作会通过
`asyncio.to_thread` 转到工作线程。Docker 通过独立子进程执行，容器内部又是独立进程。

`asyncio` 解决大量等待型任务的调度，不等于多线程；`to_thread` 才会切到线程池；
Docker 和多 worker 属于进程层。

### 22. 为什么 REST 和 SSE 都需要？

REST 返回稳定快照，例如 Run 当前状态、历史产物和完整最终结果；SSE 推送阶段变化和
文本增量，减少前端轮询。

持久事件先写 `run_events`，带 Run 内递增 `seq`，断线后可以补发。Token 级文本增量是
瞬时事件，不全部落库；断线后虽然看不到每个增量，但可以通过 Run 快照恢复最终答案。

### 23. 完整查询结果为什么不直接塞进模型或 SQLite JSON？

大结果直接进上下文会增加 Token、延迟和幻觉风险；大 JSON 长期写 SQLite 也会造成库膨胀
和分页困难。当前完整结果写 CSV，SQLite 保存元数据和最多 50 行预览，State 只保存
`datasetId` 等引用。

前端可以分页和导出；Agent 需要细节时通过历史结果工具按需读取；复杂全量统计通过 SQL
聚合或 Docker Python 处理。

### 24. Agent 怎样避免无限循环和重复失败？

代码限制 Agent 轮数、Schema 搜索次数、SQL 执行次数和修复次数，并把剩余预算告诉模型。
SQL 失败以 observation 返回，模型可以修复或换工具。

当前这些默认上限多为 50，只能证明“不会无限”，不能证明成本合理。工程上应进一步增加
总 Token、总耗时、连续重复动作检测和分任务预算，普通查询通常只允许少量 SQL 修复。

---

## C 级：设计、研究与工程能力

### 25. 为什么选 Chroma、BM25 和 RRF，而不是只用向量检索？

Chroma 适合本地单机项目，嵌入进程、持久化简单，不需要额外维护服务。BM25 对表名、
字段名、状态值和缩写等精确词更可靠；向量召回补充同义表达；RRF 避免直接相加两个尺度
不同的分数。

这是当前规模下的取舍，不是生产环境唯一答案。数据量和多实例需求增长后，可以把向量层
替换为 pgvector、Milvus 或托管检索服务，而上层 `KnowledgeRetriever` 接口保持稳定。

### 26. 如果数据量扩大到千万级，怎样调整？

先区分“业务表千万行”和“向量文档千万条”。业务表千万行时，不把数据拉进 Python：
建立与查询模式匹配的索引和分区，把过滤、Join、聚合下推 MySQL，使用 EXPLAIN 和慢查询
定位瓶颈；长任务改成异步作业，结果写对象存储或分析型数据库。

如果分析复杂度和并发继续增长，可以引入 ClickHouse/Spark 等分析引擎。向量文档千万条
时需要独立向量服务、批量增量索引、分片、过滤和召回评测。SQLite、进程内 TaskRegistry
和本地 Chroma 都要替换为共享数据库、任务队列和独立检索服务。

### 27. 你参考过哪些开源项目或论文？具体学了什么？

只能讲真正读过并能指出模块的内容。回答结构应是：

```text
项目/论文名称
→ 我读了哪个模块
→ 原设计解决什么问题
→ 我在项目里采用或没有采用什么
→ 为什么
```

不能只说“了解过某个 Agent，它很极简”。如果目前只深入了 LangGraph 的 State、
checkpoint 和 ToolNode，就诚实讲这些；等真正阅读其他项目的 memory、context
compaction、hook 或 plugin 代码后，再把项目名写进回答。

### 28. AI Coding 参与了多少？怎样证明你拥有这份代码？

可以诚实说 AI 帮助生成了部分代码，但我负责需求边界、架构取舍、代码审查、测试和问题
定位。证明所有权的方式不是强调“我也手写了”，而是能够：

- 从 API 入口画到数据库和图节点。
- 解释每张核心表和每个安全边界。
- 修改一个需求时指出受影响模块。
- 复现并定位一次真实故障。
- 说出当前实现的三个缺陷和改进顺序。
- 用测试和评测证明改动没有破坏行为。

如果以上做不到，就说明还没有真正接管 AI 生成的代码。

### 29. 当前项目最大的三个不足是什么？

第一，Python 版缺少完整离线评测，无法量化 ReAct、RAG 和上下文压缩的收益。第二，
自动长期记忆虽然有代码，但没有接入主链。第三，任务调度、SQLite 和本地 Chroma 都是
单机设计，多实例部署会遇到任务所有权、事件广播和共享存储问题。

回答不足后要给优先级：先补评测，因为没有基线就无法判断后续优化；再清理简历与未接线
能力；最后根据真实负载决定是否引入分布式组件。

### 30. LangGraph、插件、Skill 和多 Agent 应该怎样取舍？

这些不是互相替代的同一层概念。LangGraph负责运行时编排和状态恢复；Tool/插件负责扩展
外部能力；Skill更像可复用的任务说明、知识和流程封装；多 Agent 是把不同角色的上下文和
决策拆开。

当前销售分析场景一个 Agent 加一组边界清晰的工具就够了。只有当不同子任务需要不同模型、
权限、上下文或可独立并行评测时，才值得拆多 Agent。不能为了“更先进”增加通信和调试成本。

### 31. 如果面试官说“LangGraph 已经过时”，应该怎么回答？

不与面试官争论行业结论，也不马上否定自己的项目。可以回答：

> 我理解现在很多 Coding Agent 更强调原生 Tool Calling、插件、Skill、Hook 和长任务
> 上下文管理。我的项目使用 LangGraph，不是为了把所有能力写成固定节点，而是用它管理
> State、条件路由、人工中断和 checkpoint；真正的分析步骤仍由工具循环动态决定。
> 如果后续运行时只剩简单 while loop，我也会评估去掉框架；当前保留它是因为中断恢复和
> 显式状态仍然有实际价值。

重点是解释适用条件，而不是追逐名词。

### 32. 遇到不会的问题怎么回答？

先确认问题，再区分“当前实现”和“通用原理”：

> 这个框架内部机制我目前没有完整研究过。就当前项目，我能确认的是……，代码位置是……。
> 如果需要支持您说的并行场景，我会先验证……，而不会直接假设它按完成顺序覆盖。

不要用模糊概念填空，也不要把未来方案说成已经实现。承认边界并给出验证方法，比错误地
猜一个答案更可靠。

---

## 面试前红线

以下任意一条说错，都可能让面试官怀疑项目所有权：

1. 当前是真实 **7 个业务节点**，不是 5 个或 6 个。
2. `run_id == LangGraph thread_id`，`conversation_id` 不是线程 ID。
3. `messages` 有 reducer；并行写普通字段会冲突，不是最后完成者覆盖。
4. SQLite 不是只有一张消息表。
5. RAG 是 BM25 + Chroma + RRF，当前没有独立 reranker。
6. Docker 通过 CLI 启动，但确实配置了容器隔离。
7. 长期记忆自动抽取和向量召回没有完整接入主链。
8. Python 分析上限是 5 万行，不能说成海量数据处理平台。
9. Python 重构版还没有正式对照评测，不能宣称准确率提升。
10. AI 参与开发不是问题，看不懂和无法验证代码才是问题。

## 闭卷验收

面试前必须完成三轮，每轮都不看文档：

1. 90 秒画出请求链路和 7 节点图。
2. 5 分钟讲清 State、checkpoint、SQLite 三层状态。
3. 手算一次 BM25/向量候选的 RRF 排名。
4. 说出 7 张核心表“一行表示什么”。
5. 解释跨轮摘要和 Run 内工具压缩的区别。
6. 背出 Docker 六项安全限制。
7. 回答“为什么重构、效果是否提升”，全程不使用未经评测的结论。
8. 由同学连续追问 20 分钟；任何答案如果只出现技术名词、没有代码或数据结构，判为未通过。

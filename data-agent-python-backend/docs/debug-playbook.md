# DataAgent 调试与故障排查手册

> 目标：出现问题时，不猜、不加静默兜底，而是从可观测数据定位到具体请求、run、阶段和外部依赖。

---

## 1. 先记住排查主线

```text
request_id
  ↓ HTTP请求
conversation_id
  ↓ 一段会话
run_id
  ↓ 一次分析运行
stage / attempt
  ↓ 哪个图节点、第几次尝试
tool_call_id / query_id / result_set_id
  ↓ 具体工具、SQL和结果
error_code + traceback
```

最重要的是`run_id`。绝大多数分析问题都应该先找到它，然后串联日志和数据库记录，而不是在所有日志中搜索一句自然语言问题。

---

## 2. 开始排查前的五项检查

### 2.1 服务是否真的使用了预期配置

启动日志会输出模型、Base URL、API Key是否配置、思考模式、业务数据库驱动和日志文件位置。先确认启动的是当前代码和当前虚拟环境：

```bash
uv run python --version
uv run python -c "from app.config import get_settings; print(get_settings().model_dump())"
```

第二条会打印配置，其中可能包含敏感凭据，只能在本机排查，不要贴到公开Issue或面试材料中。

### 2.2 健康检查

```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

它证明FastAPI和应用SQLite可用，但不能单独证明LLM、Embedding、MySQL、Chroma和Docker都可用。

### 2.3 OpenAPI是否包含目标接口

打开：

```text
http://127.0.0.1:8000/docs
```

如果接口不存在，先检查路由是否注册、API前缀是否改变，而不是调业务逻辑。

### 2.4 日志位置

默认日志：

```text
data/logs/app.log
data/logs/app.log.1
...
```

常用命令：

```bash
tail -f data/logs/app.log
rg "runId=run_xxx" data/logs/app.log*
rg "ERROR|Traceback|failed" data/logs/app.log*
```

### 2.5 数据文件位置

| 数据 | 默认位置 |
|---|---|
| Agent应用库 | `data/app.db` |
| LangGraph快照 | `data/checkpoints.db` |
| 文档索引清单 | `data/knowledge-manifest.db` |
| Chroma | `data/chroma/` |
| SQL完整结果 | `data/datasets/` |
| Python分析产物 | `data/python-analysis/` |

路径可以被配置覆盖。不要看到默认文件存在，就断定当前进程正在使用它。

---

## 3. 手工发起并追踪一次请求

### 3.1 创建会话

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/conversations \
  -H 'Content-Type: application/json' \
  -d '{"title":"调试会话"}'
```

保存返回的`id`，例如`conv_xxx`。

### 3.2 创建run

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/conversations/conv_xxx/runs \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: debug-order-channel-001' \
  -d '{"query":"统计各销售渠道的已完成订单数","idempotencyKey":"debug-order-channel-001"}'
```

预期返回`202`：

```json
{
  "runId": "run_xxx",
  "conversationId": "conv_xxx",
  "status": "queued",
  "eventsUrl": "/api/v1/runs/run_xxx/events"
}
```

`X-Request-ID`追踪创建run的HTTP请求，`idempotencyKey`防止重复点击产生两次run。二者用途不同。

### 3.3 查看run快照

```bash
curl -s http://127.0.0.1:8000/api/v1/runs/run_xxx
```

重点字段：

- `status`：运行生命周期；
- `resultMode`：业务结果类型；
- `currentStage`：最后记录的阶段；
- `stages`：每个阶段的尝试和耗时；
- `queries`：生成/执行过的SQL；
- `retrieval`：最终持久化的Schema和知识召回；
- `error`：顶层失败信息。

### 3.4 查看SSE事件

```bash
curl -N http://127.0.0.1:8000/api/v1/runs/run_xxx/events
```

断线续传：

```bash
curl -N -H 'Last-Event-ID: 12' http://127.0.0.1:8000/api/v1/runs/run_xxx/events
```

它应只返回`seq > 12`的事件。

---

## 4. 用SQLite检查真实状态

进入SQLite：

```bash
sqlite3 data/app.db
```

先设置显示格式：

```sql
.headers on
.mode column
.nullvalue NULL
```

### 4.1 run主记录

```sql
SELECT id, conversation_id, status, result_mode, current_stage,
       duration_ms, error_code, error_message, event_seq, version
FROM analysis_runs
WHERE id = 'run_xxx';
```

如果API和这里的状态不一致，先确认API进程与`sqlite3`打开的是同一个文件。

### 4.2 阶段记录

```sql
SELECT stage, attempt, status, duration_ms, error_code, error_message
FROM stage_runs
WHERE run_id = 'run_xxx'
ORDER BY started_at, attempt;
```

判断方法：

- 某阶段只有`running`：执行可能中断，或收尾没有成功落库；
- 同一阶段多个`attempt`：发生过重试；
- run已经`failed`但stage仍`running`：检查失败收尾是否找到了正确`current_stage`；
- 所有stage完成但run仍`running`：检查执行器的`_complete()`是否执行。

### 4.3 工具调用

```sql
SELECT sequence, tool_name, status, duration_ms,
       arguments_json, result_json, error_json
FROM tool_calls
WHERE run_id = 'run_xxx'
ORDER BY sequence;
```

用它回答：

1. 模型到底选择了哪个工具？
2. 参数是什么？
3. 工具是否真正完成？
4. 工具结果是否进入了下一轮上下文？

### 4.4 SQL记录

```sql
SELECT id, step_id, attempt, status, row_count, result_set_id,
       sql, safety, error
FROM queries
WHERE run_id = 'run_xxx'
ORDER BY created_at;
```

`queries`为空有三种常见情况：模型从未请求SQL、SQL在执行前被校验阻断、执行器在持久化查询记录前异常。

### 4.5 Artifact

```sql
SELECT id, stage, type, summary, created_at
FROM artifacts
WHERE run_id = 'run_xxx'
ORDER BY created_at;
```

需要查看payload时再查单条，避免终端被大JSON刷屏：

```sql
SELECT json_pretty(payload)
FROM artifacts
WHERE id = 'artifact_xxx';
```

如果当前SQLite版本不支持`json_pretty`，直接查询`payload`或使用`json_extract(payload, '$.字段')`。

### 4.6 SSE事件源数据

```sql
SELECT seq, type, stage, created_at, data
FROM run_events
WHERE run_id = 'run_xxx'
ORDER BY seq;
```

前端没显示某条过程信息时，先做二分：

- `run_events`中没有：后端没有生成或落库；
- `run_events`中存在、SSE没有：检查续传游标和SSE接口；
- SSE中存在、前端没有：检查前端事件解析和状态更新。

### 4.7 结果集

```sql
SELECT id, total_rows, json_array_length(rows) AS preview_rows,
       truncated, storage_type, file_path, expires_at
FROM result_sets
WHERE run_id = 'run_xxx';
```

若`storage_type='csv'`，继续确认`file_path`存在。文件过期或超配额后，系统会删除CSV并把记录降级为`storage_type='sqlite'`，此时只能读取保留的预览。

---

## 5. 如何阅读Python traceback

示例结构：

```text
Traceback (most recent call last):
  File ".../executor.py", line ..., in _consume
    ...
  File ".../analysis.py", line ..., in result
    ...
TypeError: Object of type date is not JSON serializable
```

阅读顺序：

1. 先看最后一行：异常类型和直接原因；
2. 从底部向上找第一个属于本项目`app/`的调用位置；
3. 再向上理解它由哪个入口调用；
4. 记录输入数据的类型和值，不要只盯报错行；
5. 找到数据第一次变得不符合约定的位置，修根因而非最后一行症状。

例如`date`无法JSON序列化，正确问题不是“怎样把这次`json.dumps`改到不报错”，而是明确跨层数据的序列化边界，并统一把日期、Decimal等转换为JSON安全格式。

---

## 6. 按症状排查

### 6.1 POST创建run直接返回422

检查：

1. 请求JSON是否有效；
2. `query`是否为空或超过20000字符；
3. camelCase字段是否正确；
4. OpenAPI中的`RunCreate`约束。

422发生在Pydantic校验阶段，通常还没有创建run，因此查不到`run_id`是正常的。

### 6.2 POST返回404

常见原因是`conversation_id`不存在。查询：

```sql
SELECT id, status FROM conversations WHERE id = 'conv_xxx';
```

不要通过自动创建新会话来隐藏错误ID，否则前端状态和用户历史会被拆散。

### 6.3 run长时间停在`queued`

检查顺序：

1. `TaskRegistry.start()`是否调用；
2. 日志中是否出现`analysis run started`；
3. 进程是否刚刚重启；
4. run是否命中已有幂等键，返回了旧记录；
5. 是否在多个Uvicorn worker之间使用了进程内TaskRegistry。

当前TaskRegistry仅存在于单个进程。多worker部署时，创建请求和取消请求可能落到不同进程，不能视为分布式可靠任务系统。

### 6.4 run停在`running`

先查`current_stage`、对应`stage_runs`和日志。常见外部等待：

- LLM请求；
- MySQL连接或慢查询；
- Embedding请求；
- Docker分析；
- SQLite写锁。

再核对每一层是否都有超时。不要只给前端加超时，因为后端任务仍可能继续运行。

### 6.5 run变成`service_restarted`

服务启动时会把遗留的`queued/running`记录标为失败，因为进程内`asyncio.Task`已经丢失。当前项目不会自动续跑普通分析任务；用户应显式重试并生成新run。

### 6.6 LLM返回401

检查：

1. `DATA_AGENT_LLM_API_KEY`是否属于当前Base URL；
2. Key是否包含引号、空格或已过期；
3. 模型名是否由该服务提供；
4. Kimi产品会员凭证是否被误当作开放平台API Key；
5. 启动日志中的`apiKeyConfigured`和`baseUrl`；
6. 是否修改配置后没有重启。

禁止在日志中打印完整API Key。只能记录“是否配置”和必要的服务端request ID。

### 6.7 “LLM输出达到Token上限”

OpenAI兼容响应的`finish_reason=length`意味着模型只返回了前半段。项目会拒绝把截断JSON当成完整结果。

排查：

- 是输入上下文过大，还是输出任务要求过多；
- 哪个LLM operation触发；
- Token usage与finish reason；
- 是否把大工具结果直接放进上下文；
- 是否应缩小结构化输出，而不是静默解析半截JSON。

### 6.8 Schema没有召回或召回错表

按顺序查：

1. `search_schema`是否真的被调用；
2. `tool_calls.arguments_json`中的查询词；
3. MySQL实时`snapshot`是否包含目标表；
4. Schema检索候选分数、Top K和邻接表扩展；
5. `schema_snapshot`和`retrieval`两个Artifact；
6. Agent之后是否调用`inspect_tables`补充字段。

如果目标表根本不在实时Schema中，问题是数据源连接或权限，不是调RRF参数。

### 6.9 业务知识召回为空

检查：

```bash
uv run data-agent-index-knowledge
```

然后确认：

- `knowledge-manifest.db`中是否有source和chunk；
- Chroma collection名和Embedding模型是否与索引时一致；
- 查询Embedding服务是否可达；
- BM25原始候选是否为空；
- 向量分数是否低于`recall_vector_min_score`；
- RRF后是否被Top K截断。

不要在召回为空时无条件返回前几篇文档，这会把问题从“可观察的空召回”变成“隐蔽的错误上下文”。

### 6.10 SQL没有生成

先判断这是否真的错误：

- 普通聊天、澄清问题和安全拦截本来就不应生成SQL；
- 模型可能先调用Schema、知识或历史工具；
- Agent达到预算后可能结束。

查看`tool_calls`和`agent.decision`事件，而不是只检查`queries`表。

### 6.11 SQL被安全策略拦截

查询`queries.safety`、`query_preview` Artifact以及`sql_validate`阶段。常见模式：

| result mode | 含义 |
|---|---|
| `blocked_wide_export` | 无约束全字段/宽表导出 |
| `blocked_sensitive_sql` | 明文读取敏感字段 |
| `blocked_schema_violation` | 表字段不存在或越过召回Schema |
| `blocked_unsafe_sql` | 非SELECT、多语句、危险函数等 |

拦截是预期结果，不应通过“捕获异常后继续执行原SQL”来修复。

### 6.12 SQL执行失败

检查三层：

1. 生成SQL：语法、别名、聚合和Join是否正确；
2. 数据库：连接、权限、超时、函数兼容性；
3. 持久化：SQL是否执行成功但保存CSV/ResultSet失败。

执行节点会把异常写进`observations`供Agent修复。`queries`表只有在执行器消费到该节点更新后才写入，因此极早期异常可能只存在于run错误和日志。

### 6.13 SQL执行成功但结果不可信

不要只看“有行返回”。核对：

- 表粒度是否正确；
- `orders`连接`order_items`后订单数是否使用`COUNT(DISTINCT orders.id)`；
- 历史售价/成本是否使用明细快照；
- 退款是否按业务口径扣除；
- 状态和时间范围是否正确；
- 最终总结中的数字能否追溯到`resultSetId`。

这是查询语义问题，不是数据库连接问题。

### 6.14 查询成功但前端没有图表

检查：

1. `analysis` Artifact中是否有`charts`；
2. `xField`、`yFields`是否都存在于结果列；
3. `resultSetId`是否属于本run；
4. 前端支持该chart type吗；
5. API presenter是否把Artifact正确组装进run详情。

后端会归一化非法结果来源，但不会凭空制造不存在的字段。

### 6.15 SSE只显示“收到请求”或没有后续事件

依次检查：

1. `run_events`是否持续新增；
2. SSE请求的`after_seq`/`Last-Event-ID`是否过大；
3. run是否已经进入终态或`waiting_review`，流因此结束；
4. 代理是否缓冲`text/event-stream`；
5. 前端是否处理`message`、`complete`和`error`三类event；
6. 前端是否把心跳注释误当JSON解析。

当前SSE是阶段和产物级事件，不是LLM逐Token输出。

### 6.16 点击取消但底层操作仍短暂运行

正常取消路径：

```text
API把run标记cancelled并写事件
→ TaskRegistry.cancel_and_wait()
→ LangGraph协程收到CancelledError
→ API删除checkpoint
```

边界：

- `to_thread()`内已经开始的同步MySQL/Chroma/CSV操作不能被强杀；
- 当前Docker普通取消没有完整子进程清理；
- SSE断开只停止观察，不取消run。

判断取消是否成功应看run终态和后台Task是否结束，不能只看底层连接是否在同一毫秒消失。

### 6.17 `database is locked`

检查：

- 是否启动了多个服务实例写同一个`app.db`；
- 是否有手工SQLite事务长时间未提交；
- Repository是否进行了过多细粒度`commit()`；
- 是否有大查询或FTS写入占住写锁；
- WAL和`busy_timeout`是否应用到当前连接。

不要无限增大timeout掩盖写入设计问题。需要从日志统计提交频率和最长事务。

### 6.18 CSV不存在或分页只能看到预览

查询`result_sets.storage_type/file_path/expires_at`：

- `csv`且文件存在：可以读取完整数据；
- `sqlite`：完整CSV已经过期或因配额被清理，只剩预览；
- `csv`但文件不存在：数据库和文件发生漂移，启动时孤儿清理无法修复这种“缺失引用文件”，应记录告警并检查删除来源。

### 6.19 Python分析失败

检查：

```bash
docker image inspect data-agent-python-sandbox:latest
docker ps -a
```

再检查Artifact中的代码、输入dataset ID、stdout/stderr和退出码。常见原因：

- 镜像未构建；
- OrbStack/Docker daemon未启动；
- 生成代码依赖镜像里没有的包；
- 输入CSV已过期；
- 超过30秒、512MB或PID限制；
- 输出文件权限问题。

不要退回宿主机直接执行模型代码来“临时跑通”。

---

## 7. 状态与结果模式速查

### 7.1 run status

| status | 含义 | 是否终态 |
|---|---|---:|
| `queued` | 已受理，后台Task尚未标记开始 | 否 |
| `running` | 图正在执行 | 否 |
| `waiting_review` | checkpoint已保存，等待人工决定 | 否 |
| `completed` | 工作流正常走到结果节点 | 是 |
| `failed` | 未处理异常导致执行失败 | 是 |
| `cancelled` | 用户主动取消 | 是 |

`completed`只说明工作流正常结束，不等于一定执行SQL。例如聊天或澄清也可以正常完成。

### 7.2 result mode

`result_mode`描述业务结果路径，例如`success`、`conversation`、`need_clarification`、安全拦截、预算耗尽或执行异常。它与run status是两个维度：

```text
status=completed + result_mode=conversation
status=completed + result_mode=blocked_prompt_injection
status=failed    + result_mode=execution_error
```

---

## 8. 数据保留和清理排查

| 数据 | 当前策略 |
|---|---|
| 完成run checkpoint | run完成后立即删除；失败会记录日志并由定时任务重试 |
| 取消run checkpoint | 取消API等待Task结束后删除 |
| 失败run checkpoint | 默认保留24小时用于排查 |
| 孤儿checkpoint | 启动和定时清理 |
| CSV结果集 | 默认168小时；超磁盘配额也会按旧到新清理 |
| CSV清理后的ResultSet | 数据库记录保留，降级为SQLite预览 |
| 会话及其run/message/artifact | 删除会话时按外键级联清理 |
| 会话FTS索引 | 删除会话时应用层显式清理 |
| memory item | 代码有180天/500条策略，但当前自动抽取和淘汰未接入主完成链路 |
| Artifact `expires_at` | 字段存在，但普通Artifact当前没有统一后台TTL清理器 |

如果面试官问“TTL是否已经生效”，必须按具体数据类型回答，不能笼统说“系统都有TTL”。

---

## 9. IDE断点怎么下

最有价值的断点顺序：

1. `app/api/routes/runs.py:create_run`
2. `app/application/run_commands.py:RunCommandService.create`
3. `app/application/executor.py:GraphAnalysisExecutor.run`
4. `app/workflow/nodes/analysis.py:agent_decide`
5. `app/workflow/tools.py:LoggingToolNode.ainvoke`
6. `app/workflow/nodes/analysis.py:sql_validate/sql_execute/result`
7. `app/application/executor.py:_persist_node_update`

异步调试时注意：停在一个断点会暂停整个解释器进程，SSE心跳和其他协程也可能停止。不要把“断点期间请求超时”误判为业务死锁。

建议Watch：

```text
run_id
state.keys()
state.get("agent_decision")
state.get("schema")
state.get("sql")
state.get("safety")
state.get("observations")
state.get("query_results")
```

---

## 10. 测试定位策略

修改后不要先跑所有外部服务。按由小到大验证：

```bash
# 纯确定性策略
uv run pytest tests/test_sql_policy.py -q

# 检索
uv run pytest tests/test_retrieval.py -q

# LLM客户端契约
uv run pytest tests/test_llm_client.py -q

# 整条HTTP + LangGraph + SQLite链路
uv run pytest tests/test_api.py -q

# 全量
uv run pytest
```

失败时加：

```bash
uv run pytest tests/test_api.py::test_name -vv -s --maxfail=1
```

- `-vv`显示更详细用例名；
- `-s`显示标准输出和日志；
- `--maxfail=1`在第一个失败处停下。

测试使用Fake依赖通过，不等于真实LLM、MySQL和Docker已配置正确。最后还需要一次真实冒烟请求。

---

## 11. 一份合格的Bug记录

```markdown
## 现象
用户看到什么，预期是什么。

## 标识
- requestId:
- conversationId:
- runId:
- resultSetId（如有）:

## 环境
- commit:
- Python版本:
- LLM provider/model:
- 数据源:

## 时间线
1. 请求时间
2. 最后成功阶段
3. 首个错误阶段

## 数据库状态
- analysis_runs:
- stage_runs:
- tool_calls:
- queries:

## 首个异常
完整异常类型、message和属于项目代码的首个栈帧。

## 已排除
列出已经验证过的假设和证据。

## 最小复现
请求JSON、必要配置和可重复步骤，删除API Key及敏感数据。
```

最差的Bug描述是“好像RAG有问题”；合格描述应是“`run_xxx`第2次`search_schema`调用返回0张表，实时Schema包含`order_items`，BM25原始分数为X，向量请求在Y处失败”。

---

## 12. 最终排查原则

1. 先判断是HTTP请求失败，还是已经受理后的后台run失败。
2. 先找到`run_id`，再看阶段、工具、SQL和结果集。
3. 先找第一个错误，不要只修最后一个连锁症状。
4. 区分“工作流正常结束”和“业务结果正确”。
5. 区分“测试替身通过”和“真实外部依赖可用”。
6. 不用默认值、空列表或假成功吞掉依赖错误。
7. 修复后补日志和自动化测试，让同类问题下次可以直接定位。

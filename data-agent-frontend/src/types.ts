// ============================================================================
// types.ts —— 项目的「数据字典」
// ----------------------------------------------------------------------------
// 这是整个前端最重要的文件之一：它用 TypeScript 的 `type` 关键字，
// 把「后端会返回什么样的数据」一一定义清楚。
//
// 为什么需要它？
//   没有类型时，你从接口拿到一个对象，得靠记忆/翻文档才知道里面有哪些字段；
//   有了类型，编辑器（VS Code）会在你写 `obj.` 的时候自动提示可用字段，
//   写错字段名直接红线报错 —— 这就是 TypeScript 的核心价值：把 bug 挡在运行前。
//
// 两个最基础的 TS 语法：
//   1) `type X = { ... }`  —— 定义一个「对象结构」（也叫接口/interface 的等价写法）
//   2) `|`  —— 联合类型，表示「这个值可以是 A 或 B 或 C」
// ============================================================================

// 应用当前显示的页面。注意这里的 `|`：它的值只可能是这 5 个字符串之一，
// 写代码时如果写 `setView('xxx')` 拼错成 `'welcom'`，TS 会立刻报错。
export type AppView = 'welcome' | 'workspace' | 'results' | 'review' | 'settings'

// 表格密度：只有两种取值，典型的「枚举式」联合类型。
export type TableDensity = 'comfortable' | 'compact'

// 「智能体」的配置信息。每个字段都标了类型：
//   - `string` 字符串（如 'default-analysis'）
//   - `boolean` 布尔值（true / false，这里表示「是否为默认」）
export type AgentProfile = { id: string; name: string; description: string; isDefault: boolean }

// 数据源（连的是哪个数据库）。
export type Datasource = { id: string; name: string; type: string; status: string; isDefault: boolean }

// 应用启动时的全局配置。
// 小知识：`Record<string, boolean>` 表示「键是字符串、值是布尔」的对象，
//   等价于 `{ [key: string]: boolean }`，用来描述「不确定有哪些 key」的字典。
export type Bootstrap = {
  defaultAgentId: string
  agents: AgentProfile[]
  recommendedQuestions: string[]
  datasources: Datasource[]
  features: Record<string, boolean>
}

// 一段「对话」的概要（列表里展示用的精简信息）。
// 注意 `lastRunId: string | null`：联合类型里加上 `null`，
//   表示「可能没有运行记录」（null 就是「空/没有」的标准写法）。
export type Conversation = {
  id: string
  title: string
  agentId: string
  datasourceId: string
  status: string
  lastRunId: string | null
  createdAt: string
  updatedAt: string
}

// 一条聊天消息。
export type Message = {
  id: string
  conversationId: string
  runId: string | null
  role: string
  content: string
  contentType: string
  createdAt: string
}

// 分析流程里「某一个阶段」的运行记录（比如「检索表结构」这一步）。
// 小知识：`errorCode?: string | null` 里的 `?` 表示这个字段「可选」——
//   有的对象有它，有的没有，TS 不会因为你没写它就报错。
export type StageRun = {
  name: string
  attempt: number
  status: string
  message: string | null
  startedAt: string | null
  completedAt: string | null
  durationMs: number | null
  errorCode?: string | null
  errorMessage?: string | null
}

// 检索到的数据表信息。`displayName?: string` 同样表示可选字段。
export type RetrievalTable = {
  name: string
  displayName?: string
  score?: number | null
  reason?: string
  columns?: Array<Record<string, unknown>>
}

// 检索到的知识文档。`score` 是相似度打分（数字）。
export type RetrievalItem = { id: string; title: string; content: string; score: number; source?: string }

// 一次检索的完整结果：表 + 关系 + 文档 + 证据。
export type Retrieval = {
  tables: RetrievalTable[]
  relations: Array<Record<string, unknown>>
  documents: RetrievalItem[]
  evidences: RetrievalItem[]
}

// 分析计划里的一个步骤。
export type PlanStep = { id: string; index?: number; title: string; objective: string; status?: string }

// 整个分析计划。
export type Plan = { goal?: string; successCriteria?: string[]; selected_tables?: string[]; steps: PlanStep[] }

// 一次 SQL 查询的结果信息（不含具体数据行）。
export type QueryResult = {
  id: string
  stepId?: string
  sql: string
  status: string
  attempt: number
  durationMs: number | null
  rowCount: number
  resultSetId: string | null
  safety: Record<string, unknown>
  error: Record<string, unknown> | null
}

// 分析中的「发现」与「指标」「图表」。
export type Finding = { id: string; title: string; description: string; severity: string }
export type Metric = { id: string; label: string; value: unknown; formattedValue: string; unit?: string; description?: string }

// 图表规格。`type` 用联合类型限定了只能是这 4 种图表。
// 这里的 `unknown` 表示「具体类型暂时不关心 / 由调用方保证」，比 `any` 更安全。
export type ChartSpec = {
  id: string
  type: 'line' | 'bar' | 'pie' | 'scatter'
  title: string
  resultSetId?: string
  xField: string
  yFields: string[]
  seriesField?: string | null
  data?: Array<Record<string, unknown>>
}

// 一份完整的分析结论。
export type Analysis = { title: string; summary: string; findings: Finding[]; metrics: Metric[]; charts: ChartSpec[] }

// 人工审核节点（当 SQL 风险高时，需要人点「通过/拒绝」）。
export type Review = {
  id: string
  runId: string
  status: string
  reason: string | null
  reviewComment: string | null
  plan: Plan | null
  query: { sql?: string; scope?: { datasource?: string; tables?: string[]; timeRange?: string }; safety?: Record<string, unknown> } | null
  createdAt: string
  reviewedAt: string | null
}

// 一次「分析运行」的完整快照 —— 这是项目里最核心的数据结构。
// 它把计划、检索、SQL、结论、审核全都装在一起。
export type AnalysisRun = {
  id: string
  conversationId: string
  retryOfRunId: string | null
  status: string
  resultMode: string | null
  question: string
  contextualizedQuestion: string | null
  currentStage: string | null
  startedAt: string | null
  completedAt: string | null
  durationMs: number | null
  stages: StageRun[]
  retrieval: Retrieval | null
  plan: Plan | null
  queries: QueryResult[]
  analysis: Analysis | null
  review: Review | null
  error: { code: string; message: string } | null
}

// 「对话详情」= 基础对话信息 + 摘要 + 消息列表 + 运行列表。
// 语法：`Conversation & { ... }` 表示「在 Conversation 的基础上，再追加这些字段」。
export type ConversationDetail = Conversation & { summary: string | null; messages: Message[]; runs: AnalysisRun[] }

// 真正的查询结果数据集（含行列数据）。前端表格就是照着这个渲染的。
export type ResultSet = {
  id: string
  columns: Array<{ name: string; label: string; dataType: string }>
  rows: Array<Record<string, unknown>>
  page: number
  pageSize: number
  returnedRows: number
  totalRows: number
  truncated: boolean
}

// SSE 实时推送过来的「事件」。AI 跑分析时，后端会一条条把进度推给前端。
export type RunEvent = {
  eventId: string
  conversationId: string
  runId: string
  // 仅数据库持久事件拥有续传游标；实时 Token 增量为 null。
  seq: number | null
  type: string
  stage: string | null
  timestamp: string
  data: Record<string, unknown>
}

// Agent 每轮可见输出：工具调用前是 narration，直接回答时是 final。
export type AgentStreamMessage = {
  id: string
  iteration: number
  text: string
  kind: 'pending' | 'narration' | 'final'
  completed: boolean
  toolNames: string[]
}

// 连接诊断里每一步的结果（设置页「ping」按钮用）。
export type PingStep = { label: string; detail: string; duration: string }

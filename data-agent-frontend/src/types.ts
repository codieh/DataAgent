export type AppView = 'welcome' | 'workspace' | 'results' | 'review' | 'settings'

export type AgentProfile = { id: string; name: string; description: string; isDefault: boolean }
export type Datasource = { id: string; name: string; type: string; status: string; isDefault: boolean }
export type Bootstrap = {
  defaultAgentId: string
  agents: AgentProfile[]
  recommendedQuestions: string[]
  datasources: Datasource[]
  features: Record<string, boolean>
}

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

export type Message = {
  id: string
  conversationId: string
  runId: string | null
  role: string
  content: string
  contentType: string
  createdAt: string
}

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

export type RetrievalTable = {
  name: string
  displayName?: string
  score?: number | null
  reason?: string
  columns?: Array<Record<string, unknown>>
}
export type RetrievalItem = { id: string; title: string; content: string; score: number; source?: string }
export type Retrieval = {
  tables: RetrievalTable[]
  relations: Array<Record<string, unknown>>
  documents: RetrievalItem[]
  evidences: RetrievalItem[]
}
export type PlanStep = { id: string; index?: number; title: string; objective: string; status?: string }
export type Plan = { goal?: string; successCriteria?: string[]; selected_tables?: string[]; steps: PlanStep[] }
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
export type Finding = { id: string; title: string; description: string; severity: string }
export type Metric = { id: string; label: string; value: unknown; formattedValue: string; unit?: string; description?: string }
export type ChartSpec = {
  id: string
  type: 'line' | 'bar' | 'pie'
  title: string
  resultSetId: string
  xField: string
  yFields: string[]
  seriesField?: string | null
}
export type Analysis = { title: string; summary: string; findings: Finding[]; metrics: Metric[]; charts: ChartSpec[] }
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
export type ConversationDetail = Conversation & { summary: string | null; messages: Message[]; runs: AnalysisRun[] }
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
export type RunEvent = {
  eventId: string
  conversationId: string
  runId: string
  seq: number
  type: string
  stage: string | null
  timestamp: string
  data: Record<string, unknown>
}
export type PingStep = { label: string; detail: string; duration: string }

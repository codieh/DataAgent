export type Conversation = {
  id: string
  title: string | null
  sdk_session_id: string | null
  created_at: string
  updated_at: string
}

export type Message = {
  id: string
  run_id: string | null
  role: 'user' | 'assistant' | string
  content: string
  created_at: string
}

export type ConversationDetail = {
  conversation: Conversation & { tenant_id: string; user_id: string }
  messages: Message[]
}

export type Run = {
  id: string
  tenant_id: string
  conversation_id: string
  status: 'running' | 'completed' | 'failed' | 'cancelled' | string
  question: string
  result_mode: string | null
  error: string | null
  started_at: string
  completed_at: string | null
}

export type ToolCall = {
  id: string
  tool_name: string
  tool_use_id: string | null
  input: Record<string, unknown>
  output: Record<string, unknown> | string | null
  status: string
  error: string | null
  started_at: string
  completed_at: string | null
}

export type RunEvent = {
  event_id: string | null
  seq: number
  type: string
  timestamp: string
  data: Record<string, unknown>
  // 逐 token 的增量事件不落库、没有 seq，只用于实时渲染，不参与断线续传。
  ephemeral: boolean
}

/** 流式增量的语义：正文、思考过程、工具入参 JSON。 */
export type StreamBlockKind = 'text' | 'thinking' | 'tool_input'

export type StreamBlock = {
  kind: StreamBlockKind
  text: string
  toolName?: string
}

/** 对话区「分析过程」里的一步：对应后端一轮 assistant 输出，可折叠展示。 */
export type NarrationStep = {
  id: string
  iteration: number
  toolNames: string[]
  completed: boolean
  text: string
}

export type RunDetail = {
  run: Run
  events: RunEvent[]
  tool_calls: ToolCall[]
}

export type ResultPage = {
  result_id: string
  columns: string[]
  rows: Array<Record<string, unknown>>
  offset: number
  limit: number
  row_count: number
  truncated: boolean
  next_cursor: string | null
}

export type AppSettings = {
  backendUrl: string
  tenantId: string
  userId: string
}

export type ConnectionState = 'unknown' | 'checking' | 'online' | 'offline'

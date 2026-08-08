import type {
  AppSettings,
  Conversation,
  ConversationDetail,
  ResultPage,
  RunEvent,
  RunDetail,
} from './types'

type RunAccepted = {
  run_id: string
  conversation_id: string
  status: string
}

export type SseEnvelope = {
  eventId: string | null
  // 增量事件没有 seq，用 -1 表示"不可续传"，避免被当成合法游标推进。
  seq: number
  type: string
  timestamp: string
  data: Record<string, unknown>
  ephemeral: boolean
}

type RawRunEvent = Partial<RunEvent> & {
  id?: string
  payload?: Record<string, unknown>
  created_at?: string
}

type RawRunDetail = Omit<RunDetail, 'events'> & { events: RawRunEvent[] }

function normalizeRunEvent(event: RawRunEvent): RunEvent {
  // 兼容后端滚动重启期间的旧快照格式；新的后端正式返回 data/timestamp。
  const data = event.data ?? event.payload ?? {}
  return {
    event_id: event.event_id ?? event.id ?? null,
    seq: Number(event.seq ?? 0),
    type: event.type ?? 'message',
    timestamp: event.timestamp ?? event.created_at ?? new Date(0).toISOString(),
    data,
    ephemeral: false,
  }
}

function endpoint(settings: AppSettings, path: string): string {
  const base = settings.backendUrl.trim().replace(/\/$/, '')
  return `${base}${path}`
}

function headers(settings: AppSettings, includeJson = false): HeadersInit {
  return {
    ...(includeJson ? { 'Content-Type': 'application/json' } : {}),
    'X-Tenant-ID': settings.tenantId,
    'X-User-ID': settings.userId,
  }
}

async function request<T>(settings: AppSettings, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(endpoint(settings, path), {
    ...init,
    headers: { ...headers(settings, Boolean(init.body)), ...init.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown; message?: string } | null
    const detail = typeof body?.detail === 'string'
      ? body.detail
      : typeof body?.detail === 'object' && body.detail !== null && 'message' in body.detail
        ? String((body.detail as { message: unknown }).message)
        : body?.message
    throw new Error(detail || `请求失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: (settings: AppSettings) => request<{ status: string }>(settings, '/api/v1/health'),
  listConversations: async (settings: AppSettings) => {
    const response = await request<{ conversations: Conversation[] }>(settings, '/api/v1/conversations')
    return response.conversations
  },
  createConversation: (settings: AppSettings, title: string) => request<{ conversation_id: string }>(settings, '/api/v1/conversations', {
    method: 'POST',
    body: JSON.stringify({ title }),
  }),
  getConversation: (settings: AppSettings, conversationId: string) =>
    request<ConversationDetail>(settings, `/api/v1/conversations/${encodeURIComponent(conversationId)}`),
  createRun: (settings: AppSettings, conversationId: string, question: string) =>
    request<RunAccepted>(settings, `/api/v1/conversations/${encodeURIComponent(conversationId)}/runs`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  getRun: async (settings: AppSettings, runId: string) => {
    const detail = await request<RawRunDetail>(settings, `/api/v1/runs/${encodeURIComponent(runId)}`)
    return { ...detail, events: detail.events.map(normalizeRunEvent) }
  },
  cancelRun: (settings: AppSettings, runId: string) => request<{ status: string }>(settings, `/api/v1/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  }),
  getResult: (settings: AppSettings, conversationId: string, resultId: string, offset = 0, limit = 50) =>
    request<ResultPage>(settings, `/api/v1/result-sets/${encodeURIComponent(resultId)}?offset=${offset}&limit=${limit}`, {
      headers: { 'X-Conversation-ID': conversationId },
    }),
  downloadResult: async (settings: AppSettings, conversationId: string, resultId: string, format: 'csv' | 'json') => {
    const response = await fetch(endpoint(settings, `/api/v1/result-sets/${encodeURIComponent(resultId)}/download?format=${format}`), {
      headers: { ...headers(settings), 'X-Conversation-ID': conversationId },
    })
    if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${resultId}.${format}`
    // Firefox 会忽略未挂载到 DOM 的锚点 click；且必须在同 tick 之后才 revoke。
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  },
}

export async function consumeRunEvents(
  settings: AppSettings,
  runId: string,
  afterSeq: number,
  onEvent: (event: SseEnvelope) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(endpoint(settings, `/api/v1/runs/${encodeURIComponent(runId)}/events?after_seq=${afterSeq}`), {
    headers: headers(settings),
    signal,
  })
  if (!response.ok || !response.body) throw new Error(`无法连接运行事件流（HTTP ${response.status}）`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventName = 'message'
  let eventId: string | null = null
  let dataLines: string[] = []

  const dispatch = () => {
    if (!dataLines.length) return
    const payload = JSON.parse(dataLines.join('\n')) as {
      event_id?: string | null
      seq?: number | null
      type?: string
      timestamp?: string
      data?: Record<string, unknown>
      ephemeral?: boolean
    }
    const ephemeral = Boolean(payload.ephemeral)
    onEvent({
      eventId: payload.event_id ?? eventId,
      seq: ephemeral ? -1 : payload.seq ?? Number(eventId ?? 0),
      type: payload.type ?? eventName,
      timestamp: payload.timestamp ?? new Date().toISOString(),
      data: payload.data ?? {},
      ephemeral,
    })
    eventName = 'message'
    eventId = null
    dataLines = []
  }

  while (!signal.aborted) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line) {
        dispatch()
      } else if (line.startsWith('event:')) {
        eventName = line.slice(6).trim()
      } else if (line.startsWith('id:')) {
        eventId = line.slice(3).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      }
    }
    if (done) {
      dispatch()
      return
    }
  }
}

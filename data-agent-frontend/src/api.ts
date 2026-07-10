import type { AnalysisRun, Bootstrap, Conversation, ConversationDetail, ResultSet, Review, RunEvent } from './types'

type RunAccepted = { runId: string; conversationId: string; status: string; eventsUrl: string }

async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { message?: string; detail?: string } | null
    throw new Error(body?.message || body?.detail || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  health: (baseUrl: string) => request<{ status: string; database: string }>(baseUrl, '/api/v1/health'),
  bootstrap: (baseUrl: string) => request<Bootstrap>(baseUrl, '/api/v1/bootstrap'),
  conversations: (baseUrl: string, q = '') =>
    request<{ items: Conversation[] }>(baseUrl, `/api/v1/conversations${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  conversation: (baseUrl: string, id: string) => request<ConversationDetail>(baseUrl, `/api/v1/conversations/${id}`),
  updateConversation: (baseUrl: string, id: string, title: string) =>
    request<Conversation>(baseUrl, `/api/v1/conversations/${id}`, {
      method: 'PATCH', body: JSON.stringify({ title }),
    }),
  createConversation: (baseUrl: string, agentId: string, datasourceId: string) =>
    request<Conversation>(baseUrl, '/api/v1/conversations', {
      method: 'POST', body: JSON.stringify({ agentId, datasourceId }),
    }),
  deleteConversation: (baseUrl: string, id: string) =>
    request(baseUrl, `/api/v1/conversations/${id}`, { method: 'DELETE' }),
  createRun: (baseUrl: string, conversationId: string, body: Record<string, unknown>) =>
    request<RunAccepted>(baseUrl, `/api/v1/conversations/${conversationId}/runs`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  run: (baseUrl: string, id: string) => request<AnalysisRun>(baseUrl, `/api/v1/runs/${id}`),
  cancelRun: (baseUrl: string, id: string) => request(baseUrl, `/api/v1/runs/${id}/cancel`, { method: 'POST' }),
  retryRun: (baseUrl: string, id: string) => request<RunAccepted>(baseUrl, `/api/v1/runs/${id}/retry`, { method: 'POST' }),
  resultSet: (baseUrl: string, id: string, page = 1, pageSize = 50) =>
    request<ResultSet>(baseUrl, `/api/v1/result-sets/${id}?page=${page}&page_size=${pageSize}`),
  approve: (baseUrl: string, id: string, comment = '') =>
    request<Review>(baseUrl, `/api/v1/reviews/${id}/approve`, { method: 'POST', body: JSON.stringify({ comment }) }),
  reject: (baseUrl: string, id: string, comment: string) =>
    request<Review>(baseUrl, `/api/v1/reviews/${id}/reject`, { method: 'POST', body: JSON.stringify({ comment }) }),
}

export async function consumeRunEvents(
  baseUrl: string,
  runId: string,
  afterSeq: number,
  signal: AbortSignal,
  onEvent: (event: RunEvent) => void,
): Promise<void> {
  const response = await fetch(
    `${baseUrl.replace(/\/$/, '')}/api/v1/runs/${runId}/events?after_seq=${afterSeq}`,
    { headers: { Accept: 'text/event-stream' }, signal },
  )
  if (!response.ok || !response.body) throw new Error(`SSE HTTP ${response.status}`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const parts = buffer.replace(/\r\n/g, '\n').split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const data = part.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
      if (data) onEvent(JSON.parse(data) as RunEvent)
    }
    if (done) return
  }
}

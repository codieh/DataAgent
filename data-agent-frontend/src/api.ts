// ============================================================================
// api.ts —— 前端与后端「说话」的地方
// ----------------------------------------------------------------------------
// 前端自己不存业务数据，所有数据都来自后端 HTTP 接口。这个文件把所有
// 「怎么调用接口」的逻辑集中封装好，组件(App.tsx)只管调用、不关心细节。
//
// 你会学到的两个重点：
//   1) 泛型函数 `request<T>()`：用 TS 的「泛型」让每个接口「返回的数据类型」各不相同
//   2) SSE 流式读取 `consumeRunEvents()`：后端一条条推数据，前端边收边画
// ============================================================================

// 复用 types.ts 里定义的类型，保证「接口返回」和「代码里用的结构」一致。
import type { AnalysisRun, Bootstrap, Conversation, ConversationDetail, ResultSet, Review, RunEvent } from './types'

// 创建分析运行时，后端返回的最小信息（只含 id/状态/事件流地址）。
type RunAccepted = { runId: string; conversationId: string; status: string; eventsUrl: string }

// ----------------------------------------------------------------------------
// 通用请求封装
// ----------------------------------------------------------------------------
// 这是整个文件里最值得反复读的一行：`<T>` 是「泛型参数」。
// 意思是「这个函数能返回任意类型 T，具体是什么，由调用方决定」。
// 例如 `request<Bootstrap>(...)` 就表示「我期望拿到一个 Bootstrap 类型的对象」，
// 如果后端返回的数据结构和 Bootstrap 对不上，TS 会在编译期就提醒你。
async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  // `fetch` 是浏览器内置的「发 HTTP 请求」函数。
  // 这里是把 baseUrl(如 http://localhost:8000) 和 path(如 /api/v1/health) 拼起来。
  // `.replace(/\/$/, '')` 用正则去掉 baseUrl 末尾多余的斜杠，避免拼出 `//`。
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
    ...init,                                              // 展开调用方传进来的配置（method、body 等）
    headers: { 'Content-Type': 'application/json', ...init?.headers }, // 默认声明「发送 JSON」
  })
  // HTTP 状态码非 2xx 时，response.ok 为 false —— 主动抛错，让调用方 catch。
  if (!response.ok) {
    // 尝试解析后端的错误体；如果解析失败就返回 null（用 .catch(() => null) 兜底）。
    const body = await response.json().catch(() => null) as { message?: string; detail?: string } | null
    throw new Error(body?.message || body?.detail || `HTTP ${response.status}`)
  }
  // `as Promise<T>` 告诉 TS「这个 JSON 就是 T 类型」，与函数签名对齐。
  return response.json() as Promise<T>
}

// ----------------------------------------------------------------------------
// 接口集合：把每个后端接口都包成一个简洁的函数
// ----------------------------------------------------------------------------
// 用 `export const api = { ... }` 导出一个对象，里面全是方法。
// 组件里只要写 `api.health(url)`、`api.conversations(url)` 即可，非常干净。
export const api = {
  // 健康检查：返回 { status, database }
  health: (baseUrl: string) => request<{ status: string; database: string }>(baseUrl, '/api/v1/health'),

  // 启动配置：返回 Bootstrap（见 types.ts）
  bootstrap: (baseUrl: string) => request<Bootstrap>(baseUrl, '/api/v1/bootstrap'),

  // 会话列表。注意这里演示了「可选参数 + 模板字符串拼 URL 参数」。
  // `q = ''` 默认值；有 q 时才拼 `?q=...`，并用 encodeURIComponent 转义特殊字符。
  conversations: (baseUrl: string, q = '') =>
    request<{ items: Conversation[] }>(baseUrl, `/api/v1/conversations${q ? `?q=${encodeURIComponent(q)}` : ''}`),

  // 单个会话详情
  conversation: (baseUrl: string, id: string) => request<ConversationDetail>(baseUrl, `/api/v1/conversations/${id}`),

  // 改会话标题：method 改成 PATCH，body 用 JSON.stringify 把对象转成字符串。
  updateConversation: (baseUrl: string, id: string, title: string) =>
    request<Conversation>(baseUrl, `/api/v1/conversations/${id}`, {
      method: 'PATCH', body: JSON.stringify({ title }),
    }),

  // 新建会话
  createConversation: (baseUrl: string, agentId: string, datasourceId: string) =>
    request<Conversation>(baseUrl, '/api/v1/conversations', {
      method: 'POST', body: JSON.stringify({ agentId, datasourceId }),
    }),

  // 删除会话（DELETE 方法，无返回体）
  deleteConversation: (baseUrl: string, id: string) =>
    request(baseUrl, `/api/v1/conversations/${id}`, { method: 'DELETE' }),

  // 发起一次分析运行
  createRun: (baseUrl: string, conversationId: string, body: Record<string, unknown>) =>
    request<RunAccepted>(baseUrl, `/api/v1/conversations/${conversationId}/runs`, {
      method: 'POST', body: JSON.stringify(body),
    }),

  // 拉取某次运行的完整快照
  run: (baseUrl: string, id: string) => request<AnalysisRun>(baseUrl, `/api/v1/runs/${id}`),

  // 取消 / 重试运行
  cancelRun: (baseUrl: string, id: string) => request(baseUrl, `/api/v1/runs/${id}/cancel`, { method: 'POST' }),
  retryRun: (baseUrl: string, id: string) => request<RunAccepted>(baseUrl, `/api/v1/runs/${id}/retry`, { method: 'POST' }),

  // 分页拉取某结果集的数据行（默认第 1 页、每页 50 行）
  resultSet: (baseUrl: string, id: string, page = 1, pageSize = 50) =>
    request<ResultSet>(baseUrl, `/api/v1/result-sets/${id}?page=${page}&page_size=${pageSize}`),

  // 审核：通过 / 拒绝
  approve: (baseUrl: string, id: string, comment = '') =>
    request<Review>(baseUrl, `/api/v1/reviews/${id}/approve`, { method: 'POST', body: JSON.stringify({ comment }) }),
  reject: (baseUrl: string, id: string, comment: string) =>
    request<Review>(baseUrl, `/api/v1/reviews/${id}/reject`, { method: 'POST', body: JSON.stringify({ comment }) }),
}

// ----------------------------------------------------------------------------
// SSE 流式读取（Server-Sent Events）
// ----------------------------------------------------------------------------
// 普通接口：「请求一次 → 拿到一份完整结果」。
// SSE 流式：「建一个长连接 → 后端像发短信一样，一条条把事件推过来」。
// AI 分析进度条、逐字输出，靠的就是它。
//
// 参数解释：
//   baseUrl      后端地址
//   runId        这次分析运行的 id
//   afterSeq     从「第几条之后」开始收（断线重连时用，避免重复）
//   signal       AbortSignal，用来「取消」这个连接（用户点停止时）
//   onEvent      每收到一条事件就调用的回调（前端在这里更新界面）
export async function consumeRunEvents(
  baseUrl: string,
  runId: string,
  afterSeq: number,
  signal: AbortSignal,
  onEvent: (event: RunEvent) => void,
): Promise<void> {
  // 发一个「我要收事件流」的请求，Accept 头声明接受 text/event-stream。
  const response = await fetch(
    `${baseUrl.replace(/\/$/, '')}/api/v1/runs/${runId}/events?after_seq=${afterSeq}`,
    { headers: { Accept: 'text/event-stream' }, signal },
  )
  if (!response.ok || !response.body) throw new Error(`SSE HTTP ${response.status}`)

  // response.body 是一个「可读流」，getReader() 让我们可以一点点读。
  const reader = response.body.getReader()
  const decoder = new TextDecoder()  // 把字节流解码成字符串
  let buffer = ''                     // 累积还没处理完的零散数据

  // 无限循环：一直读到流结束（done === true）。
  while (true) {
    const { done, value } = await reader.read()
    // 把这次读到的字节解码后追加到 buffer。stream: true 表示「后面还有，别急着收尾」。
    buffer += decoder.decode(value, { stream: !done })
    // SSE 协议里，事件之间用「空行(\n\n)」分隔，所以按 \n\n 切块。
    const parts = buffer.replace(/\r\n/g, '\n').split('\n\n')
    buffer = parts.pop() ?? ''  // 最后一块可能不完整，留到下次循环继续拼
    for (const part of parts) {
      // 每块里找以 `data:` 开头的行，去掉前缀、trim 空白，拼回完整 JSON 字符串。
      const data = part.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
      if (data) onEvent(JSON.parse(data) as RunEvent)  // 解析成事件对象，交给回调
    }
    if (done) return  // 流结束，退出函数
  }
}

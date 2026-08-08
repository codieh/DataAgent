import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, consumeRunEvents, type SseEnvelope } from './api'
import type {
  AppSettings,
  ConnectionState,
  Conversation,
  ConversationDetail,
  Message,
  ResultPage,
  RunDetail,
  StreamBlock,
  StreamBlockKind,
  NarrationStep,
  ToolCall,
} from './types'
import './App.css'

const SETTINGS_KEY = 'data-agent-claude-sdk-frontend.settings'
const DEFAULT_SETTINGS: AppSettings = {
  // 空字符串表示走 Vite 的 /api 代理；部署到同源静态站点时也能直接工作。
  backendUrl: import.meta.env.VITE_BACKEND_URL ?? '',
  tenantId: import.meta.env.VITE_TENANT_ID ?? 'local-tenant',
  userId: import.meta.env.VITE_USER_ID ?? 'local-user',
}

const STATUS_LABELS: Record<string, string> = {
  running: '分析中',
  completed: '已完成',
  failed: '执行失败',
  cancelled: '已取消',
}

function loadSettings(): AppSettings {
  const raw = localStorage.getItem(SETTINGS_KEY)
  if (!raw) return DEFAULT_SETTINGS
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) as Partial<AppSettings> }
  } catch {
    return DEFAULT_SETTINGS
  }
}

function parseTime(value: string): Date | null {
  let normalized = value.includes(' ') ? value.replace(' ', 'T') : value
  // 后端时间戳带显式时区偏移（如 +00:00）或 Z；无偏移的朴素时间按 UTC 处理。
  // 注意：不能对已是 +00:00 的串追加 Z，否则会变成非法的 "+00:00Z"。
  if (!/[zZ]$/.test(normalized) && !/[+-]\d{2}:\d{2}$/.test(normalized)) {
    normalized += 'Z'
  }
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatTime(value: string | null | undefined): string {
  if (!value) return ''
  const date = parseTime(value)
  if (!date) return value
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function dataString(data: Record<string, unknown> | undefined, ...keys: string[]): string {
  if (!data) return ''
  for (const key of keys) {
    if (data[key] !== undefined && data[key] !== null) return String(data[key])
  }
  return ''
}

function lastEventOfType(events: Array<{ type: string; data: Record<string, unknown> }>, type: string): Record<string, unknown> {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].type === type) return events[index].data
  }
  return {}
}

function blockIndex(data: Record<string, unknown>): number {
  const value = Number(data.index)
  return Number.isFinite(value) ? value : 0
}

/** Anthropic content block 类型 -> 前端展示语义。 */
function blockKind(blockType: string, fallback: StreamBlockKind = 'text'): StreamBlockKind {
  if (blockType === 'thinking' || blockType === 'redacted_thinking') return 'thinking'
  if (blockType === 'tool_use' || blockType === 'server_tool_use') return 'tool_input'
  if (blockType === 'text') return 'text'
  return fallback
}

/** 按 content block 下标排序后拼接，保证多段文本的顺序与模型输出一致。 */
function joinBlocks(blocks: Record<number, StreamBlock>, kind: StreamBlockKind): string {
  return Object.keys(blocks)
    .map(Number)
    .sort((left, right) => left - right)
    .map((index) => blocks[index])
    .filter((block) => block.kind === kind)
    .map((block) => block.text)
    .join(kind === 'text' ? '' : '\n')
}

// 流式增量事件只驱动实时渲染，不进入可续传的事件时间线。
const STREAM_EVENT_TYPES = ['assistant.message.delta', 'assistant.turn.start', 'assistant.block.start', 'assistant.block.stop']

const TOOL_LABELS: Record<string, string> = {
  search_schema: '查找数据表',
  inspect_tables: '读取字段信息',
  search_business_knowledge: '查找业务规则',
  set_analysis_goal: '明确分析目标',
  execute_sql: '执行查询',
  inspect_result: '读取查询结果',
  analyze_result: '分析查询结果',
  search_history: '查找历史记录',
  rewrite_core_memory: '更新记忆',
}

function toolLabel(toolName: string): string {
  const normalized = toolName.replace('mcp__data_agent__', '')
  return TOOL_LABELS[normalized] ?? normalized.replaceAll('_', ' ')
}

function eventLabel(type: string): string {
  const labels: Record<string, string> = {
    'run.started': '运行开始',
    'run.completed': '分析完成',
    'run.failed': '运行失败',
    'run.cancelled': '运行已取消',
    'agent.initialized': 'Agent 已初始化',
    'agent.system': '系统状态',
    'agent.task.started': '任务开始',
    'agent.task.completed': '任务完成',
    'agent.task.failed': '任务失败',
    'agent.task.stopped': '任务停止',
    'agent.task.notification': '任务通知',
    'assistant.message': '模型说明',
    'assistant.message.delta': 'Agent 流式输出',
    'assistant.turn.start': 'Agent 开始输出',
    'assistant.block.start': '输出片段开始',
    'assistant.block.stop': '输出片段结束',
    'assistant.completed': 'Agent 输出完成',
    'tool.requested': '调用工具',
    'tool.completed': '工具返回',
    'tool.failed': '工具失败',
    'context.compaction.started': '上下文压缩',
    'schema.discovered': '发现表结构',
    'schema.inspected': '读取表结构',
    'knowledge.searched': '检索业务知识',
    'sql.validation_failed': 'SQL 安全校验未通过',
    'sql.failed': 'SQL 执行失败',
    'sql.executed': 'SQL 执行完成',
    'result.inspected': '读取结果',
    'artifact.created': '生成分析产物',
    'artifact.failed': '产物生成失败',
    'agent.message': '模型消息',
    'history.searched': '检索历史',
    'memory.updated': '更新记忆',
    'stream.overflow': '流式续传',
  }
  return labels[type] ?? type
}

function Icon({ name }: { name: 'plus' | 'search' | 'send' | 'stop' | 'settings' | 'download' | 'refresh' | 'chevron' | 'database' | 'spark' }) {
  const paths: Record<string, string> = {
    plus: 'M12 5v14M5 12h14',
    search: 'm21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z',
    send: 'm4 4 16 8-16 8 3-8-3-8ZM7 12h9',
    stop: 'M7 7h10v10H7z',
    settings: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4ZM19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.1h-2.6v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1A1.7 1.7 0 0 0 8 15a1.7 1.7 0 0 0-1.5-1H6v-2.6h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5v-.1h2.6v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.1V14h-.1a1.7 1.7 0 0 0-1.5 1Z',
    download: 'M12 4v11m0 0 4-4m-4 4-4-4M5 20h14',
    refresh: 'M20 11a8 8 0 0 0-14.9-3M5 5v4h4M4 13a8 8 0 0 0 14.9 3M19 19v-4h-4',
    chevron: 'm9 5 7 7-7 7',
    database: 'M4 6c0-1.1 3.6-2 8-2s8 .9 8 2-3.6 2-8 2-8-.9-8-2Zm0 0v6c0 1.1 3.6 2 8 2s8-.9 8-2V6m-16 6v6c0 1.1 3.6 2 8 2s8-.9 8-2v-6',
    spark: 'm12 3 1.4 5.6L19 10l-5.6 1.4L12 17l-1.4-5.6L5 10l5.6-1.4L12 3Z',
  }
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true"><path d={paths[name]} /></svg>
}

function ConversationList({
  conversations,
  activeId,
  search,
  onSearch,
  onSelect,
  onNew,
}: {
  conversations: Conversation[]
  activeId: string | null
  search: string
  onSearch: (value: string) => void
  onSelect: (id: string) => void
  onNew: () => void
}) {
  const filtered = conversations.filter((item) => (item.title ?? '未命名分析').toLowerCase().includes(search.toLowerCase()))
  return <aside className="sidebar">
    <button className="new-analysis" onClick={onNew}><Icon name="plus" /> 新建分析</button>
    <label className="search-box">
      <Icon name="search" />
      <input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="搜索会话" />
      <kbd>⌘ K</kbd>
    </label>
    <div className="sidebar-heading"><span>历史会话</span><span className="count-badge">{filtered.length}</span></div>
    <nav className="conversation-list" aria-label="历史会话">
      {filtered.length ? filtered.map((conversation) => <button
        className={`conversation-item ${activeId === conversation.id ? 'is-active' : ''}`}
        key={conversation.id}
        onClick={() => onSelect(conversation.id)}
      >
        <span className="conversation-item-title">{conversation.title || '未命名分析'}</span>
        <span className="conversation-item-time">{formatTime(conversation.updated_at)}</span>
      </button>) : <div className="empty-sidebar">还没有匹配的会话</div>}
    </nav>
    <div className="sidebar-footer">
      <span className="sidebar-footer-label">CLAUDE SDK WORKSPACE</span>
      <span className="sidebar-footer-copy">会话、运行和结果分开持久化</span>
    </div>
  </aside>
}

function MessageList({ messages, excludeAssistantRunId }: { messages: Message[]; excludeAssistantRunId?: string | null }) {
  return <div className="message-list">
    {messages.filter((message) => !(message.role === 'assistant' && excludeAssistantRunId && message.run_id === excludeAssistantRunId)).map((message) => <article className={`message ${message.role === 'user' ? 'message-user' : 'message-assistant'}`} key={message.id}>
      <div className="message-meta"><strong>{message.role === 'user' ? '你' : 'DataAgent'}</strong><span>{formatTime(message.created_at)}</span></div>
      <div className="message-content">
        {message.role === 'assistant' ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown> : <p>{message.content}</p>}
      </div>
    </article>)}
  </div>
}

function ToolTrace({ calls, events }: { calls: ToolCall[]; events: SseEnvelope[] }) {
  const liveTools = events.filter((event) => ['tool.requested', 'tool.completed', 'tool.failed'].includes(event.type))
  if (!calls.length && !liveTools.length) return null
  return <details className="trace-panel detail-panel">
    <summary className="detail-summary"><span>查看技术细节</span><span>{calls.length || liveTools.length} 次工具调用</span><Icon name="chevron" /></summary>
    <div className="trace-list detail-panel-body">
      {calls.map((call) => <details className="trace-card" key={call.id}>
        <summary><span className={`trace-dot trace-${call.status}`} /><strong>{toolLabel(call.tool_name)}</strong><span className="trace-status">{call.status === 'completed' ? '已完成' : call.status === 'failed' ? '失败' : '处理中'}</span><Icon name="chevron" /></summary>
        <div className="trace-body">
          <span className="trace-time">{formatTime(call.started_at)}</span>
          <pre>{JSON.stringify(call.input, null, 2)}</pre>
          {call.error ? <p className="error-copy">{call.error}</p> : null}
        </div>
      </details>)}
      {!calls.length ? liveTools.map((event) => <div className="trace-card live-trace" key={`${event.type}-${event.seq}`}>
        <span className={`trace-dot trace-${event.type === 'tool.failed' ? 'failed' : event.type === 'tool.completed' ? 'completed' : 'requested'}`} />
        <strong>{toolLabel(dataString(event.data, 'tool_name') || 'tool')}</strong>
        <span className="trace-status">{eventLabel(event.type)}</span>
      </div>) : null}
    </div>
  </details>
}

function ResultCard({
  result,
  resultNumber,
  onDownload,
}: {
  result: ResultPage
  resultNumber: number
  onDownload: (format: 'csv' | 'json') => void
}) {
  const visibleColumns = result.columns.slice(0, 8)
  return <section className="result-card">
    <div className="result-card-head">
      <div><span className="eyebrow">SQL 查询结果</span><h3>结果 {resultNumber}</h3></div>
      <div className="result-actions"><button onClick={() => onDownload('csv')}><Icon name="download" /> 下载 CSV</button><button onClick={() => onDownload('json')}><Icon name="download" /> 下载 JSON</button></div>
    </div>
    <div className="result-stats"><strong>{result.row_count.toLocaleString()}</strong><span>行结果</span><span className="result-note">当前展示前 {result.rows.length} 行{result.truncated ? '，完整数据可下载' : ''}</span></div>
    {result.rows.length ? <div className="table-wrap"><table><thead><tr>{visibleColumns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{result.rows.map((row, rowIndex) => <tr key={`${result.result_id}-${rowIndex}`}>{visibleColumns.map((column) => <td key={column} title={displayValue(row[column])}>{displayValue(row[column])}</td>)}</tr>)}</tbody></table></div> : <div className="empty-result">结果集没有可预览的行</div>}
    {result.columns.length > visibleColumns.length ? <div className="table-footnote">字段较多，当前预览前 {visibleColumns.length} 列；下载文件包含全部字段。</div> : null}
  </section>
}

function ArtifactCollection({
  results,
  conversationId,
  onDownload,
}: {
  results: ResultPage[]
  conversationId: string
  onDownload: (conversationId: string, resultId: string, format: 'csv' | 'json') => void
}) {
  if (!results.length) return null
  return <details className="artifact-collection">
    <summary className="artifact-collection-head"><div><span className="eyebrow">数据产物</span><h3>SQL 查询结果</h3></div><span>{results.length} 份结果</span><Icon name="chevron" /></summary>
    <div className="artifact-collection-list">{results.map((result, index) => <ResultCard
      key={result.result_id}
      result={result}
      resultNumber={index + 1}
      onDownload={(format) => onDownload(conversationId, result.result_id, format)}
    />)}</div>
  </details>
}

function ActivityTimeline({ events }: { events: SseEnvelope[] }) {
  const visible = events.filter((event) => {
    if (event.type === 'assistant.message' || STREAM_EVENT_TYPES.includes(event.type)) return false
    // 兼容后端修复前已经落库的 SDK 内部状态事件，避免历史 Run 仍被空消息刷屏。
    if (event.type === 'agent.system' || event.type === 'agent.message') {
      return Boolean(dataString(event.data, 'text', 'summary', 'message', 'error'))
    }
    return true
  })
  if (!visible.length) return null
  return <details className="activity-panel detail-panel">
    <summary className="detail-summary"><span>查看运行日志</span><span>{visible.length} 条记录</span><Icon name="chevron" /></summary>
    <div className="activity-list detail-panel-body">{visible.slice(-24).map((event) => <div className="activity-row" key={`${event.seq}-${event.type}`}>
      <span className={`activity-node ${event.type.endsWith('failed') || event.type === 'run.failed' ? 'is-failed' : event.type === 'run.completed' ? 'is-done' : ''}`} />
      <div className="activity-copy"><strong>{eventLabel(event.type)}</strong><span>{activityDetail(event)}</span></div>
      <time>{formatTime(event.timestamp)}</time>
    </div>)}</div>
  </details>
}

function activityDetail(event: SseEnvelope): string {
  if (event.type === 'tool.requested' || event.type === 'tool.completed') return toolLabel(dataString(event.data, 'tool_name'))
  if (event.type === 'sql.executed') return `${dataString(event.data, 'row_count', 'rowCount')} 行 · ${dataString(event.data, 'artifact_ref', 'result_ref', 'resultRef')}`
  if (event.type === 'run.failed') return dataString(event.data, 'error')
  if (event.type === 'context.compaction.started') return 'SDK 正在压缩上下文，完成后会继续当前运行'
  if (event.type.startsWith('agent.task.')) return dataString(event.data, 'description', 'status', 'task_id')
  return dataString(event.data, 'summary', 'message', 'error')
}

function LiveDraft({ thinking, toolDrafts }: { thinking: string; toolDrafts: StreamBlock[] }) {
  if (!thinking && !toolDrafts.length) return null
  return <section className="live-draft">
    {thinking ? <details className="draft-card">
      <summary><span className="draft-dot" />思考过程<span className="draft-hint">{thinking.length} 字</span></summary>
      <pre className="draft-body">{thinking}</pre>
    </details> : null}
    {toolDrafts.map((block, index) => <div className="draft-card draft-tool" key={`${block.toolName ?? 'tool'}-${index}`}>
      <div className="draft-head"><span className="draft-dot is-tool" />正在生成参数<strong>{(block.toolName ?? '').replace('mcp__data_agent__', '') || 'tool'}</strong></div>
      <pre className="draft-body">{block.text}</pre>
    </div>)}
  </section>
}

function AgentNarrationList({ steps }: { steps: NarrationStep[] }) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => new Set())
  const allCollapsed = steps.length > 0 && steps.every((step) => collapsedIds.has(step.id))

  function toggle(id: string) {
    setCollapsedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    setCollapsedIds(allCollapsed ? new Set() : new Set(steps.map((step) => step.id)))
  }

  if (!steps.length) return null
  return <section className="agent-narration-list" aria-label="Agent 分析过程">
    <div className="agent-narration-toolbar">
      <strong>分析过程</strong>
      <button type="button" onClick={toggleAll}>{allCollapsed ? '全部展开' : '全部收起'}</button>
    </div>
    {steps.map((step) => {
      const collapsed = collapsedIds.has(step.id)
      return <section className={`agent-narration ${collapsed ? 'is-collapsed' : ''} ${step.completed ? '' : 'is-live'}`} key={step.id}>
        <button
          className="agent-narration-toggle"
          type="button"
          aria-expanded={!collapsed}
          aria-controls={`${step.id}-content`}
          onClick={() => toggle(step.id)}
        >
          <span className="narration-step-index">第 {step.iteration} 步</span>
          <em className="narration-step-hint">{step.toolNames.length ? step.toolNames.map((name) => name.replace('mcp__data_agent__', '')).join(' + ') : step.completed ? '过程说明' : '正在输出'}</em>
          <Icon name="chevron" />
        </button>
        {!collapsed ? <div className="agent-narration-content" id={`${step.id}-content`}>
          {step.text
            ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{step.text}</ReactMarkdown>
            : step.toolNames.length
              ? <p className="narration-tool-only">本步通过工具调用获取数据，结果见下方结果区。</p>
              : null}
          {!step.completed ? <span className="stream-caret" aria-hidden="true" /> : null}
        </div> : null}
      </section>
    })}
  </section>
}

function SettingsPanel({ settings, onSave, onClose }: { settings: AppSettings; onSave: (settings: AppSettings) => void; onClose: () => void }) {
  const [draft, setDraft] = useState(settings)
  return <div className="settings-overlay" role="dialog" aria-modal="true">
    <section className="settings-panel">
      <div className="settings-head"><div><span className="eyebrow">RUNTIME CONFIG</span><h2>连接设置</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭">×</button></div>
      <p className="settings-copy">身份头由前端注入，后端据此隔离会话和结果。生产环境应由认证网关生成，不要把用户自填 Header 当成鉴权。</p>
      <label>后端地址<input value={draft.backendUrl} onChange={(event) => setDraft({ ...draft, backendUrl: event.target.value })} placeholder="留空使用当前站点 /api 代理" /></label>
      <label>租户 ID<input value={draft.tenantId} onChange={(event) => setDraft({ ...draft, tenantId: event.target.value })} /></label>
      <label>用户 ID<input value={draft.userId} onChange={(event) => setDraft({ ...draft, userId: event.target.value })} /></label>
      <div className="settings-actions"><button className="button-ghost" onClick={onClose}>取消</button><button className="button-primary" onClick={() => onSave(draft)}>保存设置</button></div>
    </section>
  </div>
}

function TitleBar() {
  const ipc = typeof window !== 'undefined' ? window.ipcRenderer : undefined
  return <div className="titlebar">
    <span className="titlebar-title">DataAgent · Claude SDK</span>
    <div className="titlebar-controls">
      <button type="button" onClick={() => ipc?.send('window:minimize')} aria-label="最小化">—</button>
      <button type="button" onClick={() => ipc?.send('window:maximize')} aria-label="最大化">▢</button>
      <button type="button" onClick={() => ipc?.send('window:close')} aria-label="关闭">×</button>
    </div>
  </div>
}

function App() {
  const [settings, setSettings] = useState<AppSettings>(loadSettings)
  const [connection, setConnection] = useState<ConnectionState>('unknown')
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [conversationDetail, setConversationDetail] = useState<ConversationDetail | null>(null)
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null)
  const [events, setEvents] = useState<SseEnvelope[]>([])
  const [results, setResults] = useState<Record<string, ResultPage>>({})
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  // 当前这一轮尚未收到权威快照的增量缓冲，按 content block 下标累积。
  const [liveBlocks, setLiveBlocks] = useState<Record<number, StreamBlock>>({})
  // 当前这一轮助手输出是否在进行中（用于把「正在输出」的步挂到列表末尾）。
  const [turnActive, setTurnActive] = useState(false)
  // 流式过程中从 assistant.block.start 捕获的工具名，落库快照不含工具名，只能实时拿。
  const [liveToolNames, setLiveToolNames] = useState<string[]>([])
  const streamAbort = useRef<AbortController | null>(null)
  const streamToken = useRef(0)

  useEffect(() => () => streamAbort.current?.abort(), [])

  async function checkHealth(nextSettings = settings) {
    setConnection('checking')
    try {
      await api.health(nextSettings)
      setConnection('online')
    } catch {
      setConnection('offline')
    }
  }

  async function loadConversations(nextSettings = settings) {
    try {
      const list = await api.listConversations(nextSettings)
      setConversations(list)
      setConnection('online')
    } catch (reason) {
      setConnection('offline')
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  // 仅首次挂载时拉取初始设置对应的连接与会话列表；后续设置变更由 saveSettings 主动触发。
  useEffect(() => {
    void checkHealth()
    void loadConversations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function loadResult(resultId: string, conversationId: string, nextSettings = settings) {
    try {
      const page = await api.getResult(nextSettings, conversationId, resultId)
      setResults((current) => ({ ...current, [resultId]: page }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  function resultIds(items: Array<{ type: string; data: Record<string, unknown> }>): string[] {
    return [...new Set(items.filter((event) => event.type === 'sql.executed' || (event.type === 'artifact.created' && dataString(event.data, 'artifact_kind') === 'sql_result')).map((event) => dataString(event.data, 'artifact_ref', 'result_ref', 'resultRef')).filter(Boolean))]
  }

  async function loadRun(runId: string, conversationId: string, nextSettings = settings, shouldStream = true) {
    const detail = await api.getRun(nextSettings, runId)
    setRunDetail(detail)
    const restoredEvents: SseEnvelope[] = detail.events.map((event) => ({
      eventId: event.event_id,
      seq: event.seq,
      type: event.type,
      timestamp: event.timestamp,
      data: event.data,
      ephemeral: false,
    }))
    setEvents(restoredEvents)
    // 增量不落库，恢复时只能靠每轮的持久化快照；缓冲必须清空，否则会和快照重复。
    setLiveBlocks({})
    setTurnActive(false)
    setLiveToolNames([])
    for (const resultId of resultIds(restoredEvents)) void loadResult(resultId, conversationId, nextSettings)
    if (shouldStream && detail.run.status === 'running') {
      void streamRun(runId, conversationId, Math.max(0, ...restoredEvents.map((event) => event.seq)), nextSettings)
    }
  }

  async function openConversation(conversationId: string, nextSettings = settings, shouldStream = true) {
    streamAbort.current?.abort()
    streamToken.current += 1
    setError(null)
    setActiveConversationId(conversationId)
    setConversationDetail(null)
    setRunDetail(null)
    setEvents([])
    setResults({})
    setLiveBlocks({})
    setTurnActive(false)
    setLiveToolNames([])
    try {
      const detail = await api.getConversation(nextSettings, conversationId)
      setConversationDetail(detail)
      const latestRunId = [...detail.messages].reverse().find((message) => message.run_id)?.run_id
      if (latestRunId) await loadRun(latestRunId, conversationId, nextSettings, shouldStream)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  async function streamRun(runId: string, conversationId: string, afterSeq: number, nextSettings = settings) {
    streamAbort.current?.abort()
    const controller = new AbortController()
    streamAbort.current = controller
    const token = ++streamToken.current
    let cursor = afterSeq
    let resume = true
    while (resume && token === streamToken.current && !controller.signal.aborted) {
      resume = false
      try {
        await consumeRunEvents(nextSettings, runId, cursor, (event) => {
          if (token !== streamToken.current) return
          // 只有落库事件参与续传游标与时间线；增量事件没有 seq。
          if (!event.ephemeral && event.seq >= 0) {
            cursor = Math.max(cursor, event.seq)
            setEvents((current) => current.some((item) => item.seq === event.seq) ? current : [...current, event])
          }
          if (event.type === 'assistant.turn.start') {
            setLiveBlocks({})
            setTurnActive(true)
            setLiveToolNames([])
            return
          }
          if (event.type === 'assistant.block.start') {
            const index = blockIndex(event.data)
            const kind = blockKind(dataString(event.data, 'block_type'))
            const toolName = dataString(event.data, 'tool_name') || undefined
            setLiveBlocks((current) => ({ ...current, [index]: { kind, text: '', toolName } }))
            // 工具调用块会携带具体工具名；快照里没有，只能在这里实时捕获。
            if (dataString(event.data, 'block_type') === 'tool_use' && toolName) {
              setLiveToolNames((current) => (current.includes(toolName) ? current : [...current, toolName]))
            }
            return
          }
          if (event.type === 'assistant.block.stop') return
          if (event.type === 'assistant.message.delta') {
            const chunk = dataString(event.data, 'delta', 'text')
            if (!chunk) return
            const index = blockIndex(event.data)
            const raw = dataString(event.data, 'kind')
            const kind: StreamBlockKind = raw === 'thinking' || raw === 'tool_input' ? raw : 'text'
            setLiveBlocks((current) => {
              const previous = current[index]
              return { ...current, [index]: { kind: previous?.kind ?? kind, text: (previous?.text ?? '') + chunk, toolName: previous?.toolName } }
            })
            return
          }
          // 一轮结束的持久化快照才是权威内容，收到后丢弃该轮的增量缓冲避免重复渲染。
          if (event.type === 'assistant.message') {
            setLiveBlocks({})
            setTurnActive(false)
            return
          }
          if (event.type === 'sql.executed') {
            const resultId = dataString(event.data, 'artifact_ref', 'result_ref', 'resultRef')
            if (resultId) void loadResult(resultId, conversationId, nextSettings)
          }
          // 后端慢消费者时发 stream.overflow 并关闭流，期望客户端带 after_seq 续传。
          if (event.type === 'stream.overflow') resume = true
        }, controller.signal)
      } catch (reason) {
        if (!controller.signal.aborted && token === streamToken.current) setError(reason instanceof Error ? reason.message : String(reason))
        break
      }
      if (resume) await new Promise((resolve) => setTimeout(resolve, 250))
    }
    if (token === streamToken.current && !controller.signal.aborted) {
      await loadRun(runId, conversationId, nextSettings, false)
      await loadConversations(nextSettings)
    }
  }

  async function submit() {
    const text = query.trim()
    if (!text || loading) return
    setLoading(true)
    setError(null)
    try {
      let conversationId = activeConversationId
      if (!conversationId) {
        const created = await api.createConversation(settings, text.slice(0, 80))
        conversationId = created.conversation_id
        setActiveConversationId(conversationId)
      }
      const accepted = await api.createRun(settings, conversationId, text)
      setQuery('')
      await openConversation(conversationId, settings, false)
      await streamRun(accepted.run_id, conversationId, 0, settings)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setLoading(false)
    }
  }

  async function cancelRun() {
    if (!runDetail || runDetail.run.status !== 'running') return
    try {
      await api.cancelRun(settings, runDetail.run.id)
      streamAbort.current?.abort()
      await loadRun(runDetail.run.id, runDetail.run.conversation_id, settings, false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  function startNewConversation() {
    streamAbort.current?.abort()
    streamToken.current += 1
    setActiveConversationId(null)
    setConversationDetail(null)
    setRunDetail(null)
    setEvents([])
    setResults({})
    setQuery('')
    setLiveBlocks({})
    setTurnActive(false)
    setLiveToolNames([])
    setError(null)
  }

  function saveSettings(nextSettings: AppSettings) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(nextSettings))
    setSettings(nextSettings)
    setSettingsOpen(false)
    startNewConversation()
    void checkHealth(nextSettings)
    void loadConversations(nextSettings)
  }

  const currentRun = runDetail?.run
  // 每一轮的 assistant.message 都是该轮的权威快照；多轮累积成「已完成的步」。
  const completedSteps = useMemo(() => {
    const messages = events.filter((event) => event.type === 'assistant.message')
    return messages.map((event, index) => {
      const blockTypes = Array.isArray(event.data.content_block_types) ? (event.data.content_block_types as string[]) : []
      const hasTool = blockTypes.includes('tool_use')
      return {
        id: `step-${event.seq}`,
        iteration: index + 1,
        toolNames: hasTool ? ['调用工具'] : [],
        completed: true,
        text: dataString(event.data, 'text'),
      } satisfies NarrationStep
    })
  }, [events])
  const streamingText = useMemo(() => joinBlocks(liveBlocks, 'text'), [liveBlocks])
  const streamingThinking = useMemo(() => joinBlocks(liveBlocks, 'thinking'), [liveBlocks])
  const toolDrafts = useMemo(
    () => Object.keys(liveBlocks).map(Number).sort((left, right) => left - right).map((index) => liveBlocks[index]).filter((block) => block.kind === 'tool_input' && block.text),
    [liveBlocks],
  )
  // 进行中的这一轮作为末尾的「正在输出」步；快照到达后自然归入 completedSteps。
  const liveStep: NarrationStep | null = turnActive
    ? { id: 'live-step', iteration: completedSteps.length + 1, toolNames: liveToolNames, completed: false, text: streamingText }
    : null
  const narrationSteps = liveStep ? [...completedSteps, liveStep] : completedSteps
  const liveSummary = dataString(lastEventOfType(events, 'run.completed'), 'summary')
  const finalMessage = [...(conversationDetail?.messages ?? [])].reverse().find((message) => message.role === 'assistant')?.content ?? ''
  const displayedSummary = liveSummary || (currentRun?.status === 'completed' ? finalMessage : '')
  const streamingAnswer = currentRun?.status === 'running' ? streamingText : ''
  // 已完成运行的助手回答会同时存在于会话消息和下方结论卡片，只在结论卡片保留一份。
  const displayedAssistantRunId = currentRun?.status === 'completed' ? currentRun.id : null
  const busy = loading || currentRun?.status === 'running'
  const resultConversationId = currentRun?.conversation_id ?? activeConversationId
  const connectionLabel = connection === 'online' ? '已连接' : connection === 'checking' ? '连接中' : connection === 'offline' ? '离线' : '未检查'

  return <div className="app-frame">
    <TitleBar />
    <header className="topbar">
      <div className="brand"><img src="/assets/logo-horizontal.png" alt="DataAgent" /><span className="brand-caption">CLAUDE SDK</span></div>
      <div className={`connection connection-${connection}`}><span />{connectionLabel}</div>
      <div className="topbar-actions"><span className="identity-chip">{settings.tenantId} / {settings.userId}</span><button className="settings-button" onClick={() => setSettingsOpen(true)} aria-label="打开设置"><Icon name="settings" /></button></div>
    </header>
    <div className="app-body">
      <ConversationList conversations={conversations} activeId={activeConversationId} search={search} onSearch={setSearch} onSelect={(id) => void openConversation(id)} onNew={startNewConversation} />
      <main className="workspace">
        <div className="workspace-header">
          <div><span className="eyebrow">自然语言分析</span><h1>{conversationDetail?.conversation.title || '新的数据分析'}</h1></div>
          {currentRun ? <div className={`run-status status-${currentRun.status}`}><span />{STATUS_LABELS[currentRun.status] ?? currentRun.status}</div> : null}
        </div>
        <div className="workspace-scroll">
          {!conversationDetail && !events.length ? <section className="welcome">
            <div className="welcome-mark"><Icon name="spark" /></div>
            <h2>把业务问题交给<br /><em>DataAgent</em></h2>
            <p>从自然语言到可验证的 SQL 结果。Claude Agent SDK 负责循环与工具调用，系统负责租户隔离、结果持久化和安全校验。</p>
            <div className="suggestions"><button onClick={() => setQuery('分析最近三个月各销售渠道的订单金额趋势')}><span>01</span>分析最近三个月各销售渠道的订单金额趋势<Icon name="chevron" /></button><button onClick={() => setQuery('找出复购率最高的用户群体，并说明计算口径')}><span>02</span>找出复购率最高的用户群体，并说明计算口径<Icon name="chevron" /></button></div>
          </section> : null}
          {conversationDetail ? <MessageList messages={conversationDetail.messages} excludeAssistantRunId={displayedAssistantRunId} /> : null}
          {currentRun || events.length ? <section className="live-run">
            <div className="live-run-heading"><div><span className="eyebrow">当前分析</span><h2>{currentRun?.question || '正在恢复分析'}</h2></div>{currentRun?.status === 'running' ? <button className="stop-button" onClick={() => void cancelRun()}><Icon name="stop" /> 停止分析</button> : null}</div>
            {narrationSteps.length ? <details className="model-process">
              <summary className="detail-summary"><span>查看模型过程</span><span>{narrationSteps.length} 个阶段</span><Icon name="chevron" /></summary>
              <AgentNarrationList steps={narrationSteps} />
            </details> : null}
            <LiveDraft thinking={streamingThinking} toolDrafts={toolDrafts} />
            {currentRun?.status === 'running' && narrationSteps.length === 0 ? <div className="live-waiting"><span className="spinner" />等待模型输出…</div> : null}
            {displayedSummary || streamingAnswer ? <section className={`summary-card ${streamingAnswer ? 'summary-live' : ''}`}><div className="panel-label"><span>{streamingAnswer ? '正在生成回答' : '分析结论'}</span><span>{streamingAnswer ? '实时更新' : '已完成'}</span></div><ReactMarkdown remarkPlugins={[remarkGfm]}>{displayedSummary || streamingAnswer}</ReactMarkdown>{streamingAnswer ? <span className="stream-caret" aria-hidden="true" /> : null}</section> : null}
            <ActivityTimeline events={events} />
            <ToolTrace calls={runDetail?.tool_calls ?? []} events={events} />
            {resultConversationId ? <ArtifactCollection
              results={Object.values(results)}
              conversationId={resultConversationId}
              onDownload={(conversationId, resultId, format) => void api.downloadResult(settings, conversationId, resultId, format)}
            /> : null}
          </section> : null}
          {error ? <div className="error-banner"><strong>请求没有完成</strong><span>{error}</span><button onClick={() => setError(null)}>×</button></div> : null}
        </div>
        <form className="composer" onSubmit={(event) => { event.preventDefault(); void submit() }}>
          <textarea value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() } }} placeholder="描述你想分析的业务问题…" disabled={Boolean(currentRun?.status === 'running')} rows={3} />
          <div className="composer-foot"><span><Icon name="database" /> 只读业务数据库 · 完整结果可下载</span><button className="send-button" disabled={!query.trim() || busy} aria-label="发送">{busy ? <span className="spinner" /> : <Icon name="send" />}</button></div>
        </form>
      </main>
    </div>
    {settingsOpen ? <SettingsPanel settings={settings} onSave={saveSettings} onClose={() => setSettingsOpen(false)} /> : null}
  </div>
}

export default App

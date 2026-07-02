import { useEffect, useRef, useState, startTransition } from 'react'
import './App.css'
import { api, consumeRunEvents } from './api'
import { Icon } from './components/Icon'
import { ResultsScreen, ReviewScreen, SettingsScreen, WelcomeScreen, WorkspaceScreen } from './screens'
import type { AnalysisRun, AppView, Bootstrap, Conversation, ConversationDetail, PingStep, ResultSet, RunEvent } from './types'

const DEFAULT_BACKEND = 'http://localhost:8000'

function App() {
  const streamRef = useRef<AbortController | null>(null)
  const [view, setView] = useState<AppView>('welcome')
  const [backendUrl, setBackendUrl] = useState(() => localStorage.getItem('data-agent.backend-url') || DEFAULT_BACKEND)
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversation, setConversation] = useState<ConversationDetail | null>(null)
  const [run, setRun] = useState<AnalysisRun | null>(null)
  const [resultSet, setResultSet] = useState<ResultSet | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [query, setQuery] = useState('')
  const [humanReview, setHumanReview] = useState(false)
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('正在连接后端')
  const [error, setError] = useState<string | null>(null)
  const [pingRunning, setPingRunning] = useState(false)
  const [pingSteps, setPingSteps] = useState<PingStep[]>([])
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null)

  async function refreshShell() {
    try {
      const [health, boot, list] = await Promise.all([
        api.health(backendUrl), api.bootstrap(backendUrl), api.conversations(backendUrl),
      ])
      setConnected(health.status === 'ok')
      setBootstrap(boot)
      setConversations(list.items)
      setStatus('准备就绪')
      setError(null)
    } catch (reason) {
      setConnected(false)
      setStatus('后端连接失败')
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  useEffect(() => { void refreshShell() }, [backendUrl])
  useEffect(() => () => streamRef.current?.abort(), [])

  async function loadResult(nextRun: AnalysisRun, page = 1) {
    const resultSetId = [...nextRun.queries].reverse().find((item) => item.resultSetId)?.resultSetId
    setResultSet(resultSetId ? await api.resultSet(backendUrl, resultSetId, page) : null)
  }

  async function refreshRun(runId: string, navigate = true) {
    const nextRun = await api.run(backendUrl, runId)
    startTransition(() => setRun(nextRun))
    if (navigate && nextRun.status === 'waiting_review') setView('review')
    if (nextRun.status === 'completed') {
      await loadResult(nextRun)
      if (navigate) setView('results')
    }
    if (navigate && (nextRun.status === 'failed' || nextRun.status === 'cancelled')) setView('workspace')
    return nextRun
  }

  async function watchRun(runId: string, afterSeq = 0) {
    streamRef.current?.abort()
    const controller = new AbortController()
    streamRef.current = controller
    try {
      await consumeRunEvents(backendUrl, runId, afterSeq, controller.signal, (event) => {
        setEvents((current) => current.some((item) => item.seq === event.seq) ? current : [...current, event].slice(-240))
        if (event.type === 'stage.started') setStatus(String(event.data.message || '正在分析'))
        if (event.type === 'artifact.created' || event.type === 'review.required' || event.type.startsWith('run.')) {
          void refreshRun(runId)
        }
      })
      await refreshRun(runId)
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : String(reason))
        setStatus('流式连接中断，可从运行快照恢复')
        await refreshRun(runId).catch(() => undefined)
      }
    }
  }

  async function submit() {
    const text = query.trim()
    if (!text) return
    setError(null)
    setStatus('正在创建分析任务')
    setView('workspace')
    let target = conversation
    if (!target) {
      const created = await api.createConversation(
        backendUrl,
        bootstrap?.defaultAgentId || 'default-analysis',
        bootstrap?.datasources.find((item) => item.isDefault)?.id || 'sales-db',
      )
      target = await api.conversation(backendUrl, created.id)
      setConversation(target)
    }
    const accepted = await api.createRun(backendUrl, target.id, {
      query: text,
      humanReviewEnabled: humanReview,
      idempotencyKey: crypto.randomUUID(),
    })
    setConversation(await api.conversation(backendUrl, target.id))
    setRun({
      id: accepted.runId, conversationId: accepted.conversationId, retryOfRunId: null, status: accepted.status,
      resultMode: null, question: text, contextualizedQuestion: text, currentStage: null, startedAt: null,
      completedAt: null, durationMs: null, stages: [], retrieval: null, plan: null, queries: [], analysis: null,
      review: null, error: null,
    })
    setEvents([])
    setQuery('')
    void watchRun(accepted.runId)
    void refreshShell()
  }

  async function openConversation(item: Conversation) {
    streamRef.current?.abort()
    const detail = await api.conversation(backendUrl, item.id)
    setConversation(detail)
    setResultSet(null)
    setEvents([])
    if (item.lastRunId) {
      const latest = await refreshRun(item.lastRunId, false)
      setView('workspace')
      if (!['completed', 'failed', 'cancelled'].includes(latest.status)) void watchRun(latest.id)
    } else {
      setRun(null)
      setView('workspace')
    }
  }

  function newConversation() {
    streamRef.current?.abort()
    setConversation(null)
    setRun(null)
    setResultSet(null)
    setEvents([])
    setQuery('')
    setView('welcome')
  }

  async function decideReview(approved: boolean, comment = '') {
    if (!run?.review) return
    if (approved) await api.approve(backendUrl, run.review.id, comment)
    else await api.reject(backendUrl, run.review.id, comment)
    setView('workspace')
    void watchRun(run.id, events[events.length - 1]?.seq || 0)
  }

  async function cancelRun() {
    if (!run) return
    streamRef.current?.abort()
    await api.cancelRun(backendUrl, run.id)
    await refreshRun(run.id)
  }

  async function retryRun() {
    if (!run) return
    const accepted = await api.retryRun(backendUrl, run.id)
    setView('workspace')
    setEvents([])
    await refreshRun(accepted.runId)
    void watchRun(accepted.runId)
  }

  async function renameConversation(item: Conversation, title: string) {
    await api.updateConversation(backendUrl, item.id, title)
    await refreshShell()
    if (conversation?.id === item.id) setConversation(await api.conversation(backendUrl, item.id))
  }

  async function deleteConversation(item: Conversation) {
    await api.deleteConversation(backendUrl, item.id)
    if (conversation?.id === item.id) newConversation()
    setPendingDelete(null)
    await refreshShell()
  }

  async function ping() {
    setPingRunning(true)
    setPingSteps([])
    const started = performance.now()
    try {
      const health = await api.health(backendUrl)
      const elapsed = `${Math.round(performance.now() - started)}ms`
      setPingSteps([
        { label: 'HTTP 连接', detail: backendUrl, duration: elapsed },
        { label: '应用状态', detail: health.status, duration: elapsed },
        { label: 'SQLite', detail: health.database, duration: elapsed },
      ])
      setConnected(true)
    } catch (reason) {
      setConnected(false)
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setPingRunning(false) }
  }

  const navigation = {
    onNavigate: setView,
    onNew: newConversation,
    conversations,
    activeConversationId: conversation?.id,
    onOpenConversation: openConversation,
    onRenameConversation: renameConversation,
    onDeleteConversation: setPendingDelete,
  }
  const agentId = bootstrap?.defaultAgentId || 'default-analysis'

  let screen
  if (view === 'welcome') screen = <WelcomeScreen {...navigation} query={query} connected={connected} prompts={bootstrap?.recommendedQuestions || []} error={error} onQueryChange={setQuery} onSubmit={submit} />
  else if (view === 'workspace') screen = <WorkspaceScreen {...navigation} query={query} conversation={conversation} run={run} events={events} connected={connected} status={status} onQueryChange={setQuery} onSubmit={submit} onStop={cancelRun} onRetry={retryRun} onViewResults={() => setView('results')} />
  else if (view === 'results') screen = <ResultsScreen {...navigation} run={run} resultSet={resultSet} backendUrl={backendUrl} query={query} onQueryChange={setQuery} onSubmit={submit} onResultPage={(page) => run && loadResult(run, page)} onBackToProcess={() => setView('workspace')} />
  else if (view === 'review') screen = <ReviewScreen {...navigation} run={run} onApprove={() => decideReview(true)} onReject={(comment) => decideReview(false, comment)} />
  else screen = <SettingsScreen {...navigation} backendUrl={backendUrl} agentId={agentId} agents={bootstrap?.agents || []} humanReview={humanReview} connected={connected} pingRunning={pingRunning} pingSteps={pingSteps} onBackendUrlChange={(value) => { localStorage.setItem('data-agent.backend-url', value); setBackendUrl(value) }} onAgentIdChange={() => undefined} onHumanReviewChange={setHumanReview} onPing={ping} />

  return <>
    {screen}
    {pendingDelete ? <div className="confirm-backdrop" role="presentation" onMouseDown={() => setPendingDelete(null)}>
      <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
        <span className="confirm-icon"><Icon name="info" size={22} /></span>
        <div><h2 id="delete-dialog-title">删除这段对话？</h2><p>“{pendingDelete.title}”及其分析记录将被永久删除，此操作无法撤销。</p></div>
        <div className="confirm-actions"><button type="button" onClick={() => setPendingDelete(null)}>取消</button><button className="danger-button" type="button" onClick={() => void deleteConversation(pendingDelete)}>确认删除</button></div>
      </section>
    </div> : null}
  </>
}

export default App

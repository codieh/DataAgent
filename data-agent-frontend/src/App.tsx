// ============================================================================
// App.tsx —— 整个应用的「大脑」
// ----------------------------------------------------------------------------
// 这是项目里最大、也最能学到东西的文件。它把各个 Screen（页面）组装起来，
// 管理所有「会变化的数据」（叫 state / 状态），并处理「点一下 → 发请求 → 更新界面」。
//
// 本文件集中展示了 React 的 4 个核心 Hook：
//   - useState    ：声明一个「会触发界面重画」的变量
//   - useEffect   ：在「挂载后 / 依赖变化时」执行副作用（如发请求）
//   - useRef      ：存一个「变了也不重画」的值（常用于 DOM 引用、请求控制器）
//   - startTransition：把某次更新标记为「低优先级」，避免卡住输入
//
// 建议阅读顺序：① 顶部 import 与常量 → ② 一堆 useState（看有哪些状态）
//               → ③ refreshShell（怎么拉数据）→ ④ submit（点发送的完整链路）
//               → ⑤ 底部 return（怎么根据 view 切换页面）
// ============================================================================

import { useEffect, useRef, useState, startTransition } from 'react'
import './App.css'
import { api, consumeRunEvents } from './api'
import { Icon } from './components/Icon'
import { ResultsScreen, ReviewScreen, SettingsScreen, WelcomeScreen, WorkspaceScreen } from './screens'
// `import type` 只导入「类型」，不会生成运行时代码，是 TS 的最佳实践。
import type { AgentStreamMessage, AnalysisRun, AppView, Bootstrap, Conversation, ConversationDetail, PingStep, ResultSet, RunEvent } from './types'

// 后端默认地址。真实项目里通常会放到环境变量(.env)，这里写死方便演示。
const DEFAULT_BACKEND = 'http://localhost:8000'

// 组件函数。React 应用就是「一个根组件(App)里层层嵌套子组件」。
function App() {
  // ---------- useRef：不触发重画的「把手」 ----------
  // 流式连接的控制器。用它来「随时取消正在进行的 SSE 请求」。
  // useRef 的值存在 .current 上；改它 React 不会重画界面（这正是我们要的）。
  const streamRef = useRef<AbortController | null>(null)
  // 用于「防止过期请求覆盖新结果」的计数器（见 loadResult）。
  const resultRequestRef = useRef(0)
  // 当前选中的结果集 id 的「最新值」副本（在异步回调里读 .current 拿最新，不踩闭包陷阱）。
  const selectedResultSetIdRef = useRef<string | null>(null)
  // SSE 断点只记录持久事件的正序号，不能被 Token 增量等临时事件覆盖。
  const lastPersistentSeqRef = useRef(0)

  // ---------- useState：会触发重画的「状态」 ----------
  // 语法：const [值, 改值的函数] = useState(初始值)
  // 任何一次 setXxx(...) 都会让组件重新执行、界面跟着变。
  const [view, setView] = useState<AppView>('welcome')  // 当前显示哪个页面
  // 小技巧：useState 可以传「函数」作初始值，只在首次执行一次（惰性初始化）。
  // 这里用来「读 localStorage，没有就用默认地址」。
  const [backendUrl, setBackendUrl] = useState(() => localStorage.getItem('data-agent.backend-url') || DEFAULT_BACKEND)
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)   // 启动配置（null = 还没拿到）
  const [conversations, setConversations] = useState<Conversation[]>([]) // 会话列表
  const [conversation, setConversation] = useState<ConversationDetail | null>(null) // 当前打开的会话
  const [run, setRun] = useState<AnalysisRun | null>(null)             // 当前分析运行
  const [resultSet, setResultSet] = useState<ResultSet | null>(null)    // 查询结果数据
  const [selectedResultSetId, setSelectedResultSetId] = useState<string | null>(null)
  const [resultLoading, setResultLoading] = useState(false)             // 结果是否在加载
  const [resultError, setResultError] = useState<string | null>(null)   // 结果加载报错
  const [events, setEvents] = useState<RunEvent[]>([])                 // 实时事件流
  // 流式结论必须绑定 Run，不能只保存裸字符串，否则切换会话时可能回退显示旧 Run 的内容。
  const [streamingAnswer, setStreamingAnswer] = useState<{ runId: string; text: string } | null>(null)
  const [agentMessages, setAgentMessages] = useState<AgentStreamMessage[]>([]) // 每轮 Agent 可见过程说明
  const [query, setQuery] = useState('')                               // 输入框文字
  const [humanReview, setHumanReview] = useState(false)                // 是否开启人工审核
  const [connected, setConnected] = useState(false)                    // 后端是否连上
  const [status, setStatus] = useState('正在连接后端')                  // 顶部状态文字
  const [error, setError] = useState<string | null>(null)             // 全局错误
  const [pingRunning, setPingRunning] = useState(false)                // 诊断进行中
  const [pingSteps, setPingSteps] = useState<PingStep[]>([])          // 诊断步骤结果
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null) // 等待确认删除的会话

  // ---------- useEffect：副作用 ----------
  // 拉取「外壳」数据：健康、启动配置、会话列表，一次性并行请求。
  async function refreshShell() {
    try {
      // Promise.all 并行发 3 个请求，都回来后再一起解构 —— 比一个个 await 快。
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
      // `reason instanceof Error` 是 TS 里判断「是不是错误对象」的常用写法，
      // 这样能安全地读 .message，否则可能是任意类型。
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  // 第一个 useEffect：依赖数组是 [backendUrl] —— 表示「backendUrl 变化时才重新执行」。
  // 首次渲染也会执行一次，所以一打开应用就自动连后端。
  useEffect(() => { void refreshShell() }, [backendUrl])
  // 第二个 useEffect：依赖数组是 [] —— 表示「只在组件挂载时执行一次」。
  // 这里用来「组件卸载时取消还在进行的流式连接」，防止内存泄漏。
  // 返回的这个函数就是「清理函数」，React 在卸载前会调用它。
  useEffect(() => () => streamRef.current?.abort(), [])

  // 读取某次运行的某个结果集（分页）。含「防过期」逻辑，是很好的进阶例子。
  async function loadResult(nextRun: AnalysisRun, page = 1, requestedId?: string | null) {
    // 从运行里收集所有可用的结果集 id
    const availableIds = nextRun.queries.flatMap((item) => item.resultSetId ? [item.resultSetId] : [])
    // 决定要看哪个结果集：指定了且合法就用指定的，否则取最后一个
    const resultSetId = requestedId && availableIds.includes(requestedId)
      ? requestedId
      : availableIds[availableIds.length - 1]
    // 关键防过期手段：每次调用把计数器 +1，记录「这是第几次请求」。
    const requestId = ++resultRequestRef.current
    selectedResultSetIdRef.current = resultSetId || null
    setSelectedResultSetId(resultSetId || null)
    setResultError(null)
    if (!resultSetId) {
      setResultSet(null)
      setResultLoading(false)
      return
    }
    setResultLoading(true)
    try {
      const nextResult = await api.resultSet(backendUrl, resultSetId, page)
      // 只有「这次请求仍是最新的(requestId 没被后来的盖掉)」才写状态，
      // 避免慢的旧请求把快的新请求结果覆盖掉。
      if (requestId === resultRequestRef.current) setResultSet(nextResult)
    } catch (reason) {
      if (requestId === resultRequestRef.current) {
        setResultSet(null)
        setResultError(reason instanceof Error ? reason.message : String(reason))
      }
    } finally {
      if (requestId === resultRequestRef.current) setResultLoading(false)
    }
  }

  // 拉取某次运行的最新快照。完成后留在会话页，详情页只由用户主动进入。
  async function refreshRun(runId: string, navigate = true) {
    const nextRun = await api.run(backendUrl, runId)
    // startTransition：把这次 setState 标记为「低优先级」。
    // 意思是「先保证用户输入流畅，这个界面的更新可以稍后做」，长列表刷新时不卡。
    startTransition(() => setRun(nextRun))
    if (navigate && nextRun.status === 'waiting_review') setView('review')
    if (nextRun.status === 'completed') {
      await loadResult(nextRun, 1, selectedResultSetIdRef.current)
    }
    if (navigate && (nextRun.status === 'failed' || nextRun.status === 'cancelled')) setView('workspace')
    return nextRun
  }

  // 监听一次运行的事件流（SSE）。这是「AI 实时进度」的来源。
  async function watchRun(runId: string, afterSeq = 0) {
    streamRef.current?.abort()  // 先取消上一条还在进行的流（避免重复）
    const controller = new AbortController()  // 新建一个「可取消」的控制器
    streamRef.current = controller
    try {
      await consumeRunEvents(backendUrl, runId, afterSeq, controller.signal, (event) => {
        // abort 与网络读取存在极短竞态；只允许当前连接更新页面，防止旧会话事件串入新会话。
        if (streamRef.current !== controller) return
        if (event.seq !== null) {
          lastPersistentSeqRef.current = Math.max(lastPersistentSeqRef.current, event.seq)
          // 回执是可审计、可回放的持久事件。临时流事件只更新实时正文，不进入回执列表。
          setEvents((current) => current.some((item) => item.eventId === event.eventId)
            ? current
            : [...current, event].slice(-240))
        }
        if (event.type === 'stage.started') setStatus(String(event.data.message || '正在分析'))
        if (event.type === 'final_answer.started') {
          setStreamingAnswer({ runId, text: '' })
        }
        if (event.type === 'final_answer.delta') {
          const delta = String(event.data.delta || '')
          setStreamingAnswer((current) => ({
            runId,
            text: current?.runId === runId ? current.text + delta : delta,
          }))
        }
        if (event.type === 'agent_message.started') {
          const id = String(event.data.messageId || '')
          if (!id) throw new Error('agent_message.started 缺少 messageId')
          setAgentMessages((current) => current.some((item) => item.id === id)
            ? current
            : [...current, {
              id,
              iteration: Number(event.data.iteration || current.length + 1),
              text: '',
              kind: 'pending',
              completed: false,
              toolNames: [],
            }])
        }
        if (event.type === 'agent_message.delta') {
          const id = String(event.data.messageId || '')
          const delta = String(event.data.delta || '')
          if (!id) throw new Error('agent_message.delta 缺少 messageId')
          setAgentMessages((current) => {
            const existing = current.find((item) => item.id === id)
            if (!existing) {
              return [...current, {
                id,
                iteration: current.length + 1,
                text: delta,
                kind: 'pending',
                completed: false,
                toolNames: [],
              }]
            }
            return current.map((item) => item.id === id ? { ...item, text: item.text + delta } : item)
          })
        }
        if (event.type === 'agent_message.completed') {
          const id = String(event.data.messageId || '')
          const kind = String(event.data.kind || '')
          const text = String(event.data.text || '')
          if (!id || !['narration', 'final'].includes(kind)) {
            throw new Error('agent_message.completed 缺少有效的 messageId 或 kind')
          }
          const completed: AgentStreamMessage = {
            id,
            iteration: Number(event.data.iteration || 0),
            text,
            kind: kind as 'narration' | 'final',
            completed: true,
            toolNames: Array.isArray(event.data.toolNames) ? event.data.toolNames.map(String) : [],
          }
          // 直接答复进入最终回答区域；过程说明则保留在 Agent 过程消息列表中。
          if (completed.kind === 'final') {
            setStreamingAnswer({ runId, text })
            setAgentMessages((current) => current.filter((item) => item.id !== id))
          } else {
            setAgentMessages((current) => current.some((item) => item.id === id)
              ? current.map((item) => item.id === id ? completed : item)
              : [...current, completed])
          }
        }
        // 某些事件代表「运行状态变了」，需要去拉最新快照刷新界面。
        if (event.type === 'artifact.created' || event.type === 'review.required' || event.type.startsWith('run.')) {
          void refreshRun(runId)
        }
      })
      await refreshRun(runId)
    } catch (reason) {
      // 如果是我们主动 abort 的，就不报错（signal.aborted 为 true）。
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : String(reason))
        setStatus('流式连接中断，可从运行快照恢复')
        await refreshRun(runId).catch(() => undefined)
      }
    }
  }

  // 用户在输入框点「发送」的完整链路：
  //   没对话就新建 → 发分析请求 → 建一个本地 run 占位 → 开始监听事件流
  async function submit() {
    const text = query.trim()
    if (!text) return  // 空输入直接返回（防御性编程）
    setError(null)
    setStreamingAnswer(null)
    setAgentMessages([])
    setStatus('正在创建分析任务')
    setView('workspace')
    let target = conversation
    if (!target) {
      // 没有当前会话：先建一个（用启动配置里的默认 agent 和数据源）
      const created = await api.createConversation(
        backendUrl,
        bootstrap?.defaultAgentId || 'default-analysis',
        bootstrap?.datasources.find((item) => item.isDefault)?.id || 'sales-db',
      )
      target = await api.conversation(backendUrl, created.id)
      setConversation(target)
    }
    // 发起一次分析运行。注意 idempotencyKey：即使重复提交也不会建出多个同样任务。
    const accepted = await api.createRun(backendUrl, target.id, {
      query: text,
      humanReviewEnabled: humanReview,
      idempotencyKey: crypto.randomUUID(),
    })
    // 先把一个「骨架」run 塞进 state，让界面立刻进入分析中状态，提升响应感。
    setConversation(await api.conversation(backendUrl, target.id))
    setRun({
      id: accepted.runId, conversationId: accepted.conversationId, retryOfRunId: null, status: accepted.status,
      resultMode: null, question: text, contextualizedQuestion: text, currentStage: null, startedAt: null,
      completedAt: null, durationMs: null, stages: [], retrieval: null, plan: null, queries: [], analysis: null,
      review: null, error: null,
    })
    setEvents([])
    setAgentMessages([])
    lastPersistentSeqRef.current = 0
    setQuery('')  // 清空输入框
    void watchRun(accepted.runId)  // 开始监听（void 表示「我不等它结束」）
    void refreshShell()            // 顺手刷新外壳（会话列表会多一条）
  }

  // 打开历史会话
  async function openConversation(item: Conversation) {
    streamRef.current?.abort()  // 先停掉旧的流
    // 在等待新会话详情期间立即移除旧 Run 的临时文本，避免加载间隙串屏。
    setStreamingAnswer(null)
    const detail = await api.conversation(backendUrl, item.id)
    setConversation(detail)
    setResultSet(null)
    selectedResultSetIdRef.current = null
    setSelectedResultSetId(null)
    setResultError(null)
    setEvents([])
    setAgentMessages([])
    lastPersistentSeqRef.current = 0
    if (item.lastRunId) {
      const latest = await refreshRun(item.lastRunId, false)
      setView('workspace')
      // 无论 Run 是否结束都打开事件流：终态 Run 会补发数据库中的全部持久事件后立即关闭，
      // 运行中 Run 则在补发历史事件后继续监听实时事件。
      void watchRun(latest.id)
    } else {
      setRun(null)
      setView('workspace')
    }
  }

  // 新建会话：把所有相关状态复位回欢迎页
  function newConversation() {
    streamRef.current?.abort()
    setStreamingAnswer(null)
    setConversation(null)
    setRun(null)
    setResultSet(null)
    selectedResultSetIdRef.current = null
    setSelectedResultSetId(null)
    setResultError(null)
    setEvents([])
    setAgentMessages([])
    lastPersistentSeqRef.current = 0
    setQuery('')
    setView('welcome')
  }

  // 人工审核：通过或拒绝
  async function decideReview(approved: boolean, comment = '') {
    if (!run?.review) return
    if (approved) await api.approve(backendUrl, run.review.id, comment)
    else await api.reject(backendUrl, run.review.id, comment)
    setView('workspace')
    void watchRun(run.id, lastPersistentSeqRef.current)  // 只从最后一条持久事件之后续传
  }

  // 取消 / 重试当前运行
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
    const resumesSameRun = accepted.runId === run.id
    // 失败节点恢复沿用原 Run，保留已经展示的步骤、工具轨迹和持久事件；
    // 只有真正创建了新 Run 时才清空过程区。
    if (!resumesSameRun) {
      setEvents([])
      setAgentMessages([])
      lastPersistentSeqRef.current = 0
    }
    setStreamingAnswer(null)
    await refreshRun(accepted.runId)
    void watchRun(
      accepted.runId,
      resumesSameRun ? lastPersistentSeqRef.current : 0,
    )
  }

  // 重命名 / 删除会话
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

  // 连接诊断（设置页的 ping 按钮）
  async function ping() {
    setPingRunning(true)
    setPingSteps([])
    const started = performance.now()  // 记录开始时间戳（毫秒）
    try {
      const health = await api.health(backendUrl)
      const elapsed = `${Math.round(performance.now() - started)}ms`  // 耗时
      setPingSteps([
        { label: 'HTTP 连接', detail: backendUrl, duration: elapsed },
        { label: '应用状态', detail: health.status, duration: elapsed },
        { label: 'SQLite', detail: health.database, duration: elapsed },
      ])
      setConnected(true)
    } catch (reason) {
      setConnected(false)
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally { setPingRunning(false) }  // finally：无论成功失败都会执行
  }

  // 把一堆「导航/操作函数」打包成 navigation 对象，下发给各个 Screen 统一使用。
  // 这种「把回调当 props 传」是 React 最典型的父子通信方式。
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
  // 正式结果来自 Run 快照；临时文本只有归属于当前 Run 时才允许参与界面回退。
  const activeStreamingAnswer = streamingAnswer && streamingAnswer.runId === run?.id
    ? streamingAnswer.text
    : ''

  // ---------- 根据 view 决定渲染哪个页面 ----------
  // 这就是「单页应用(SPA)」的核心思路：URL 不变，靠 state(view) 切换显示的组件。
  let screen
  if (view === 'welcome') screen = <WelcomeScreen {...navigation} query={query} connected={connected} prompts={bootstrap?.recommendedQuestions || []} error={error} onQueryChange={setQuery} onSubmit={submit} />
  else if (view === 'workspace') screen = <WorkspaceScreen {...navigation} query={query} conversation={conversation} run={run} events={events} streamingAnswer={activeStreamingAnswer} agentMessages={agentMessages} connected={connected} status={status} onQueryChange={setQuery} onSubmit={submit} onStop={cancelRun} onRetry={retryRun} onViewResults={() => setView('results')} />
  else if (view === 'results') screen = <ResultsScreen {...navigation} run={run} resultSet={resultSet} selectedResultSetId={selectedResultSetId} streamingAnswer={activeStreamingAnswer} resultLoading={resultLoading} resultError={resultError} backendUrl={backendUrl} query={query} onQueryChange={setQuery} onSubmit={submit} onSelectResult={(id) => run && loadResult(run, 1, id)} onResultPage={(page) => run && loadResult(run, page, selectedResultSetId)} onBackToProcess={() => setView('workspace')} />
  else if (view === 'review') screen = <ReviewScreen {...navigation} run={run} onApprove={() => decideReview(true)} onReject={(comment) => decideReview(false, comment)} />
  else screen = <SettingsScreen {...navigation} backendUrl={backendUrl} agentId={agentId} agents={bootstrap?.agents || []} humanReview={humanReview} connected={connected} pingRunning={pingRunning} pingSteps={pingSteps} onBackendUrlChange={(value) => { localStorage.setItem('data-agent.backend-url', value); setBackendUrl(value) }} onAgentIdChange={() => undefined} onHumanReviewChange={setHumanReview} onPing={ping} />

  // 最外层 return：渲染当前 screen，外加一个「删除确认」弹窗。
  // `<>...</>` 是 React 的「碎片(Fragment)」语法，用来包多个元素又不多一层 DOM。
  return <>
    {screen}
    {/* 只有当 pendingDelete 有值时才显示确认弹窗；这是「条件渲染」的常见写法 */}
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

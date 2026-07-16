import { useEffect, useMemo, useState } from 'react'
import type { AgentProfile, AnalysisRun, AppView, Conversation, ConversationDetail, PingStep, QueryResult, ResultSet, RunEvent, TableDensity } from './types'
import { Sidebar, TitleBar } from './components/AppChrome'
import { Composer } from './components/Composer'
import { Icon } from './components/Icon'

type Navigation = {
  onNavigate: (view: AppView) => void
  onNew: () => void
  conversations: Conversation[]
  activeConversationId?: string
  onOpenConversation: (conversation: Conversation) => void
  onRenameConversation: (conversation: Conversation, title: string) => void
  onDeleteConversation: (conversation: Conversation) => void
}

const stageLabels: Record<string, string> = {
  intent: '理解问题', knowledge_recall: '召回业务知识', schema_recall: '读取数据结构', planner: '制定分析计划',
  sql_generate: '生成查询', sql_validate: '安全检查', human_feedback: '等待人工确认', sql_execute: '执行查询',
  input_guard: '检查请求安全', agent_decide: '决定下一步分析', agent_schema_search: '检索相关数据表',
  agent_schema_inspect: '查看表结构', agent_knowledge_search: '检索业务知识',
  result: '整理结果', chitchat: '生成回复',
}

const sidebar = (props: Navigation, collapsed = false) => <Sidebar {...props} collapsed={collapsed} />

export function WelcomeScreen(props: Navigation & {
  query: string; connected: boolean; prompts: string[]; error: string | null
  onQueryChange: (value: string) => void; onSubmit: () => void
}) {
  const { query, connected, prompts, error, onQueryChange, onSubmit } = props
  return <div className="app-frame">
    <TitleBar connected={connected} />
    <div className="app-shell welcome-shell">
      {sidebar(props)}
      <main className="welcome-canvas">
        <div className="welcome-grid" aria-hidden="true" />
        <section className="welcome-content">
          <p className="welcome-eyebrow">DATA ANALYSIS AGENT</p>
          <h1>从一个问题开始</h1>
          <p className="welcome-copy">用自然语言查询你的数据，获得可信的洞察与解释。<br />分析过程、SQL 与结果来源都可以检查。</p>
          <div className="prompt-suggestions">{prompts.map((prompt, index) => <button key={prompt} type="button" onClick={() => onQueryChange(prompt)}><span>{String(index + 1).padStart(2, '0')}</span><strong>{prompt}</strong><Icon name="arrow-right" size={17} /></button>)}</div>
          {error ? <p className="diagnostic-warning">后端暂不可用：{error}</p> : null}
        </section>
        <aside className="vertical-manifesto"><i /><span>自然语言</span><b /><span>查询</span><b /><span>解释</span><i /></aside>
        <div className="welcome-composer-wrap"><Composer value={query} onChange={onQueryChange} onSubmit={onSubmit} /></div>
      </main>
    </div>
  </div>
}

function formatDuration(duration: number | null) {
  if (duration == null) return '—'
  return duration < 1000 ? `${duration}ms` : `${(duration / 1000).toFixed(1)}s`
}

function parseServerTime(value: string) {
  return new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
}

function ExecutionInspector({ run, events }: { run: AnalysisRun | null; events: RunEvent[] }) {
  const [tab, setTab] = useState<'process' | 'details'>('process')
  const stages = run?.stages || []
  return <aside className="execution-inspector">
    <div className="inspector-title-row"><h2>执行过程 <span>{stages.filter((item) => item.status === 'completed').length} / {stages.length || '—'}</span></h2><div className="inspector-tabs"><button className={tab === 'process' ? 'is-active' : ''} onClick={() => setTab('process')}>过程</button><button className={tab === 'details' ? 'is-active' : ''} onClick={() => setTab('details')}>详情</button></div></div>
    {tab === 'process' ? <div className="stage-timeline">{stages.map((stage) => <div className={`stage-step stage-${stage.status === 'running' ? 'active' : stage.status}`} key={`${stage.name}-${stage.attempt}`}><span className="stage-node">{stage.status === 'completed' ? <Icon name="check" size={15} /> : null}</span><div className="stage-copy"><div><strong>{stageLabels[stage.name] || stage.name}</strong><span>{formatDuration(stage.durationMs)}</span></div>{stage.status === 'running' ? <div className="active-stage-receipt"><div><b>{stage.message}</b></div><p><i /> 执行中</p></div> : null}</div></div>)}</div> : <div className="inspector-details"><h3>事件回执</h3><div className="event-receipts">{events.slice(-12).map((event) => <div key={event.eventId}><span>{event.seq}</span><b>{event.stage || 'run'}</b><em>{event.type}</em></div>)}</div></div>}
    <p className="inspector-footnote">完整结果以持久化运行快照为准。 <Icon name="info" size={14} /></p>
  </aside>
}

export function WorkspaceScreen(props: Navigation & {
  query: string; conversation: ConversationDetail | null; run: AnalysisRun | null; events: RunEvent[]
  streamingAnswer: string
  connected: boolean; status: string; onQueryChange: (value: string) => void; onSubmit: () => void; onStop: () => void
  onRetry: () => void
  onViewResults: () => void
}) {
  const { query, conversation, run, events, streamingAnswer, connected, status, onQueryChange, onSubmit, onStop } = props
  const running = run ? ['queued', 'running'].includes(run.status) : false
  // 当前 Run 的助手消息由运行卡片统一展示；同一 Run 的用户输入必须保留。
  const visibleMessages = (conversation?.messages || []).filter(
    (message) => !(message.runId === run?.id && message.role === 'assistant'),
  )
  const displayedSummary = run?.analysis?.summary || streamingAnswer
  return <div className="app-frame">
    <TitleBar title={conversation?.title || run?.question || '新建分析'} connected={connected} />
    <div className="app-shell workspace-shell">
      {sidebar(props)}
      <main className="conversation-workspace"><div className="conversation-scroll">
        {visibleMessages.map((message) => <article className={`conversation-entry ${message.role === 'user' ? 'user-entry' : 'agent-entry'}`} key={message.id}><div className="entry-meta"><strong>{message.role === 'user' ? '用户' : 'DataAgent'}</strong><span>{parseServerTime(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span></div><p>{message.content}</p></article>)}
        {run ? <article className="conversation-entry agent-entry"><div className="entry-meta"><strong>DataAgent</strong><span>{run.status}</span></div><h1>{run.analysis?.title || (streamingAnswer ? '正在生成分析结论' : running ? '正在分析数据' : '本次分析')}</h1><p className="current-action">当前步骤：{stageLabels[run.currentStage || ''] || status}</p>{displayedSummary ? <section className={`streaming-answer ${run.analysis ? 'is-complete' : ''}`} aria-live="polite"><p>{displayedSummary}</p>{!run.analysis ? <i aria-hidden="true" /> : null}</section> : null}{run.error ? <><p className="diagnostic-warning">{run.error.message}</p><button type="button" onClick={props.onRetry}>重新运行</button></> : null}{run.analysis ? <button className="view-result-button" type="button" onClick={props.onViewResults}>查看图表与数据 <Icon name="arrow-right" size={14} /></button> : null}{run.retrieval?.tables.length ? <section className="selected-tables"><div className="artifact-heading"><strong>已选择的数据表</strong></div><div className="table-artifact">{run.retrieval.tables.map((table) => <span key={table.name}><Icon name="table" size={16} />{table.displayName || table.name}</span>)}</div></section> : null}{run.queries.length ? <details className="sql-disclosure"><summary><span><Icon name="code" size={16} /> SQL 查询（{run.queries.length} 条）</span><Icon name="chevron-down" size={14} /></summary>{run.queries.map((item) => <pre key={item.id}>{item.sql}</pre>)}</details> : null}</article> : null}
      </div><div className="workspace-composer"><Composer compact value={query} running={running} placeholder="继续提出分析问题…" onChange={onQueryChange} onSubmit={onSubmit} onStop={onStop} /></div></main>
      <ExecutionInspector run={run} events={events} />
    </div>
  </div>
}

function ResultChart({ run, resultSet, selectedResultSetId }: { run: AnalysisRun; resultSet: ResultSet | null; selectedResultSetId: string | null }) {
  const chart = run.analysis?.charts.find((item) => item.resultSetId === selectedResultSetId)
    || run.analysis?.charts.find((item) => !item.resultSetId)
  const points = useMemo(() => {
    const rows = chart?.data?.length ? chart.data : resultSet?.rows
    if (!chart || !rows?.length) return ''
    const values = rows.map((row) => Number(row[chart.yFields[0]])).filter(Number.isFinite)
    if (!values.length) return ''
    const min = Math.min(...values), max = Math.max(...values), span = max - min || 1
    return values.map((value, index) => `${24 + index / Math.max(1, values.length - 1) * 716},${238 - (value - min) / span * 176}`).join(' ')
  }, [chart, resultSet])
  const rowCount = chart?.data?.length || resultSet?.totalRows || 0
  return <div className="trend-chart"><div className="chart-title"><strong>{chart?.title || '查询结果概览'}</strong><span><i /> {chart?.yFields.join(' / ') || '暂无图表建议'}</span></div>{points ? <svg viewBox="0 0 770 270" role="img">{[55, 95, 135, 175, 215].map((y) => <line key={y} x1="24" x2="740" y1={y} y2={y} className="chart-grid-line" />)}<polyline points={points} className="sales-line" /></svg> : <div className="chart-watermark">{rowCount}</div>}</div>
}

type ColumnHint = { min: number; max: number; align: 'left' | 'right'; numeric: boolean; date: boolean; wide: boolean }

const NUMERIC_TYPES = new Set(['integer', 'int', 'bigint', 'smallint', 'tinyint', 'decimal', 'numeric', 'real', 'double', 'float', 'number', 'money', 'currency', 'percent', 'ratio', 'long'])
const DATE_TYPES = new Set(['date', 'datetime', 'timestamp', 'time', 'timestamptz'])

function describeColumn(column: { name: string; label?: string; dataType?: string }): ColumnHint {
  const name = column.name.toLowerCase()
  const label = (column.label || column.name).toLowerCase()
  const dt = (column.dataType || '').toLowerCase()
  const numeric = NUMERIC_TYPES.has(dt)
  const date = DATE_TYPES.has(dt)
  const wide = /(name|名称|描述|地址|address|addr|desc|description|remark|备注|memo|title|标题|content|内容|detail|详情|summary|摘要|note|说明|info|comment|评论)/.test(`${label}${name}`)
  const short = name.endsWith('_id') || /(^id$|^no$|^num$|^qty$|^count$|^序号$|^编号$|^数量$|^行号$|^rowid$|uuid|code$|编码)/.test(`${label}${name}`)
  let min = 130
  let max = 260
  if (short) { min = 84; max = 200 }
  else if (wide) { min = 200; max = 320 }
  else if (numeric) { min = 104; max = 220 }
  else if (date) { min = 140; max = 240 }
  return { min, max, align: numeric ? 'right' : 'left', numeric, date, wide }
}

function ResultSetSwitcher({ queries, selectedId, onSelect }: { queries: QueryResult[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return <nav className="result-set-switcher" aria-label="本次分析产生的数据结果">{queries.map((item, index) => <button type="button" className={item.resultSetId === selectedId ? 'is-active' : ''} key={item.id} onClick={() => onSelect(item.resultSetId!)}><span>结果 {index + 1}</span><strong>{item.rowCount} 行</strong><small>{item.stepId || `查询 ${index + 1}`}</small></button>)}</nav>
}

function FieldPanel({ columns, visible, onToggle, onClose }: { columns: ResultSet['columns']; visible: string[]; onToggle: (name: string) => void; onClose: () => void }) {
  return <div className="field-panel">
    <div className="field-panel-head"><span>显示字段 · {visible.length}/{columns.length}</span><button type="button" onClick={onClose} aria-label="收起字段面板"><Icon name="chevron-down" size={14} /></button></div>
    <div className="field-panel-list">
      {columns.map((column) => {
        const checked = visible.includes(column.name)
        return <label key={column.name} className="field-option">
          <input type="checkbox" checked={checked} onChange={() => onToggle(column.name)} />
          <span className="field-option-label" title={column.label || column.name}>{column.label || column.name}</span>
          <span className="field-option-type">{column.dataType}</span>
        </label>
      })}
    </div>
  </div>
}

function DataTable({ columns, rows, visible, density }: { columns: ResultSet['columns']; rows: Array<Record<string, unknown>>; visible: string[]; density: TableDensity }) {
  const shown = useMemo(() => columns.filter((column) => visible.includes(column.name)), [columns, visible])
  return <div className="result-table-scroll">
    <table className={`density-${density}`}>
      <thead><tr>{shown.map((column) => {
        const hint = describeColumn(column)
        return <th key={column.name} style={{ minWidth: hint.min, maxWidth: hint.max, textAlign: hint.align }} title={column.label || column.name}>{column.label || column.name}</th>
      })}</tr></thead>
      <tbody>
        {rows.length === 0
          ? <tr><td className="result-table-empty" colSpan={Math.max(1, shown.length)}>当前查询没有可预览的数据。</td></tr>
          : rows.map((row, index) => <tr key={index}>{shown.map((column) => {
            const hint = describeColumn(column)
            const raw = row[column.name]
            const text = raw == null ? '—' : String(raw)
            return <td key={column.name} style={{ minWidth: hint.min, maxWidth: hint.max, textAlign: hint.align }} title={text}>{text}</td>
          })}</tr>)}
      </tbody>
    </table>
  </div>
}

function FullscreenTable(props: {
  resultSet: ResultSet | null; selectedResultSetId: string | null
  successfulQueries: QueryResult[]; visible: string[]; density: TableDensity
  fieldPanelOpen: boolean; resultLoading: boolean; resultError: string | null
  onSelectResult: (id: string) => void; onToggleColumn: (name: string) => void
  onToggleDensity: () => void; onToggleFieldPanel: () => void; onClose: () => void
}) {
  const { resultSet, selectedResultSetId, successfulQueries, visible, density, fieldPanelOpen, resultLoading, resultError, onSelectResult, onToggleColumn, onToggleDensity, onToggleFieldPanel, onClose } = props
  return <div className="table-fullscreen-overlay" role="dialog" aria-modal="true" aria-label="数据预览">
    <div className="fullscreen-bar">
      <div className="fullscreen-title"><Icon name="table" size={16} /><strong>数据预览</strong>{resultSet ? <span>{resultSet.totalRows} 行 · 显示 {visible.length}/{resultSet.columns.length} 列</span> : null}</div>
      <div className="fullscreen-tools">
        {successfulQueries.length > 1 ? <ResultSetSwitcher queries={successfulQueries} selectedId={selectedResultSetId} onSelect={onSelectResult} /> : null}
        <button type="button" className={fieldPanelOpen ? 'is-active' : ''} onClick={onToggleFieldPanel}><Icon name="columns" size={15} />显示字段</button>
        <button type="button" onClick={onToggleDensity}><Icon name="more" size={15} />{density === 'comfortable' ? '舒适' : '紧凑'}</button>
        <button type="button" onClick={onClose}><Icon name="minimize" size={15} />退出全屏</button>
      </div>
    </div>
    <div className="fullscreen-body">
      {fieldPanelOpen && resultSet ? <FieldPanel columns={resultSet.columns} visible={visible} onToggle={onToggleColumn} onClose={onToggleFieldPanel} /> : null}
      {resultLoading
        ? <div className="result-table-scroll"><p className="result-table-state">正在加载结果…</p></div>
        : resultError
          ? <div className="result-table-scroll"><p className="result-table-state is-error">结果加载失败：{resultError}</p></div>
          : resultSet
            ? <DataTable columns={resultSet.columns} rows={resultSet.rows} visible={visible} density={density} />
            : <div className="result-table-scroll"><p className="result-table-state">当前查询没有可预览的数据。</p></div>}
    </div>
  </div>
}

export function ResultsScreen(props: Navigation & {
  run: AnalysisRun | null; resultSet: ResultSet | null; selectedResultSetId: string | null
  streamingAnswer: string
  resultLoading: boolean; resultError: string | null; backendUrl: string; query: string
  onQueryChange: (value: string) => void; onSubmit: () => void; onResultPage: (page: number) => void
  onSelectResult: (resultSetId: string) => void
  onBackToProcess: () => void
}) {
  const { run, resultSet, backendUrl } = props
  const [tab, setTab] = useState<'table' | 'sql' | 'evidence'>('table')
  const [visibleColumns, setVisibleColumns] = useState<string[]>([])
  const [showAllFindings, setShowAllFindings] = useState(false)
  const [density, setDensity] = useState<TableDensity>('comfortable')
  const [fieldPanelOpen, setFieldPanelOpen] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)

  useEffect(() => {
    if (resultSet) setVisibleColumns(resultSet.columns.map((column) => column.name))
  }, [resultSet?.id])

  if (!run?.analysis) return <WorkspaceScreen {...props} conversation={null} events={[]} streamingAnswer={props.streamingAnswer} connected status="结果尚未生成" onStop={() => undefined} onRetry={() => undefined} onViewResults={() => undefined} />
  const analysis = run.analysis
  const successfulQueries = run.queries.filter((item) => item.resultSetId)
  const selectedQuery = successfulQueries.find((item) => item.resultSetId === props.selectedResultSetId)

  function toggleColumn(name: string) {
    setVisibleColumns((current) => {
      if (current.includes(name)) return current.length === 1 ? current : current.filter((item) => item !== name)
      return [...current, name]
    })
  }

  const tableArea = props.resultLoading
    ? <div className="result-table-scroll"><p className="result-table-state">正在加载结果…</p></div>
    : props.resultError
      ? <div className="result-table-scroll"><p className="result-table-state is-error">结果加载失败：{props.resultError}</p></div>
      : resultSet
        ? <DataTable columns={resultSet.columns} rows={resultSet.rows} visible={visibleColumns} density={density} />
        : <div className="result-table-scroll"><p className="result-table-state">当前查询没有可预览的数据。</p></div>

  return <div className="app-frame"><TitleBar connected title={run.question} /><div className="app-shell results-shell">{sidebar(props)}<main className="results-canvas">
    <header className="results-header"><p><span><Icon name="check" size={14} /></span>分析完成 · {run.stages.length} 个步骤 · {formatDuration(run.durationMs)}</p><div className="results-title-row"><div><h1>{analysis.title}</h1><p>{analysis.summary}</p></div><div className="result-actions"><button onClick={() => navigator.clipboard.writeText(analysis.summary)}><Icon name="copy" size={15} />复制结论</button>{props.selectedResultSetId ? <a href={`${backendUrl}/api/v1/result-sets/${encodeURIComponent(props.selectedResultSetId)}/export?format=csv`}><Icon name="download" size={15} />下载</a> : null}</div></div></header>
    <section className="result-analysis-grid"><ResultChart run={run} resultSet={resultSet} selectedResultSetId={props.selectedResultSetId} /><aside className="key-findings"><h2>关键发现{analysis.findings.length > 3 ? <span className="findings-count">{showAllFindings ? analysis.findings.length : `前 3 / ${analysis.findings.length}`}</span> : null}</h2>{analysis.findings.slice(0, showAllFindings ? undefined : 3).map((finding, index) => <div className="finding" key={finding.id}><span>{index + 1}</span><div className="finding-body"><strong className="finding-title" title={finding.title}>{finding.title}</strong><span className="finding-desc" title={finding.description}>{finding.description}</span></div></div>)}{analysis.findings.length > 3 ? <button type="button" className="findings-toggle" onClick={() => setShowAllFindings((value) => !value)}>{showAllFindings ? '收起' : `查看全部 ${analysis.findings.length} 条`}</button> : null}{analysis.metrics[0] ? <div className="key-metric"><p>{analysis.metrics[0].label}</p><strong>{analysis.metrics[0].formattedValue}</strong><span>{analysis.metrics[0].description}</span></div> : null}</aside></section>
    {successfulQueries.length > 1 ? <ResultSetSwitcher queries={successfulQueries} selectedId={props.selectedResultSetId} onSelect={props.onSelectResult} /> : null}
    <section className="result-data-panel"><div className="data-tabs"><button className={tab === 'table' ? 'is-active' : ''} onClick={() => setTab('table')}>数据表</button><button className={tab === 'sql' ? 'is-active' : ''} onClick={() => setTab('sql')}>当前 SQL</button><button className={tab === 'evidence' ? 'is-active' : ''} onClick={() => setTab('evidence')}>分析依据</button></div>
      {tab === 'table' ? <div className="data-table-body">
        <div className="data-table-toolbar">
          <span className="data-table-count">{resultSet ? `共 ${resultSet.columns.length} 列 · 显示 ${visibleColumns.length} 列` : ''}</span>
          <div className="data-table-tools">
            <button type="button" className={fieldPanelOpen ? 'is-active' : ''} onClick={() => setFieldPanelOpen((value) => !value)}><Icon name="columns" size={15} />显示字段</button>
            <button type="button" onClick={() => setDensity((value) => value === 'comfortable' ? 'compact' : 'comfortable')}><Icon name="more" size={15} />{density === 'comfortable' ? '舒适' : '紧凑'}</button>
            <button type="button" onClick={() => setFullscreen(true)}><Icon name="expand" size={15} />全屏</button>
          </div>
        </div>
        {fieldPanelOpen && resultSet ? <FieldPanel columns={resultSet.columns} visible={visibleColumns} onToggle={toggleColumn} onClose={() => setFieldPanelOpen(false)} /> : null}
        {tableArea}
      </div> : <pre className="result-code">{tab === 'sql' ? selectedQuery?.sql || '当前结果没有关联 SQL。' : [...(run.retrieval?.documents || []), ...(run.retrieval?.evidences || [])].map((item) => `${item.title}\n${item.content}`).join('\n\n') || '本次分析未引用额外知识。'}</pre>}
      <div className="table-footer"><span>共 {resultSet?.totalRows || 0} 行{resultSet?.truncated ? '（已截断）' : ''}</span><span><button disabled={!resultSet || resultSet.page <= 1} onClick={() => props.onResultPage((resultSet?.page || 1) - 1)}>‹</button> 第 {resultSet?.page || 1} 页 <button disabled={!resultSet || resultSet.page * resultSet.pageSize >= resultSet.totalRows} onClick={() => props.onResultPage((resultSet?.page || 1) + 1)}>›</button></span></div></section>
    {/* <div className="result-composer"><Composer compact value={query} placeholder="继续追问这份结果…" onChange={onQueryChange} onSubmit={onSubmit} /></div> */}
  </main><aside className="results-toolrail"><button type="button" onClick={props.onBackToProcess}><Icon name="chart" /><span>过程</span></button><button type="button"><Icon name="database" /><span>载荷</span></button><button type="button"><Icon name="wave" /><span>事件</span></button></aside></div>
    {fullscreen ? <FullscreenTable
      resultSet={resultSet} selectedResultSetId={props.selectedResultSetId}
      successfulQueries={successfulQueries} visible={visibleColumns} density={density}
      fieldPanelOpen={fieldPanelOpen} resultLoading={props.resultLoading} resultError={props.resultError}
      onSelectResult={props.onSelectResult} onToggleColumn={toggleColumn}
      onToggleDensity={() => setDensity((value) => value === 'comfortable' ? 'compact' : 'comfortable')}
      onToggleFieldPanel={() => setFieldPanelOpen((value) => !value)} onClose={() => setFullscreen(false)}
    /> : null}
  </div>
}

export function ReviewScreen(props: Navigation & { run: AnalysisRun | null; onApprove: () => void; onReject: (comment: string) => void }) {
  const [comment, setComment] = useState('')
  const review = props.run?.review
  const plan = review?.plan || props.run?.plan
  const query = review?.query
  return <div className="app-frame review-frame"><TitleBar connected /><div className="app-shell review-shell">{sidebar(props, true)}<main className="review-document"><p className="review-status"><Icon name="pause" /> 等待你的确认</p><h1>执行这条查询前，请先审核</h1><p className="review-intro">{review?.reason}</p><section className="review-plan"><h2>执行计划</h2>{plan?.steps.map((step, index) => <div key={step.id}><span>{index + 1}</span><p>{step.objective || step.title}</p></div>)}</section><section className="sql-specimen"><div><strong>只读查询 · 已完成安全检查</strong><button onClick={() => navigator.clipboard.writeText(query?.sql || '')}><Icon name="copy" size={14} />复制 SQL</button></div><pre>{query?.sql}</pre></section><section className="query-scope"><h2>查询范围</h2><div><span><small>数据源</small>{query?.scope?.datasource || 'sales-db'}</span><span><small>涉及表</small>{query?.scope?.tables?.join(' / ') || '—'}</span><span><small>时间范围</small>{query?.scope?.timeRange || '由 SQL 条件确定'}</span></div></section><div className="safe-query"><Icon name="shield" size={36} /><div><strong>确定性安全检查已通过</strong><span>人工批准不会绕过后端 SQL 安全策略。</span></div></div></main><aside className="review-action-panel"><div><strong>{String(props.run?.stages.length || 0).padStart(2, '0')}</strong><i /><span>HUMAN CHECKPOINT</span></div><h2>是否批准 Agent 继续执行？</h2><div className="review-actions"><button className="approve-button" onClick={props.onApprove}>批准并继续</button><button className="reject-button" disabled={!comment.trim()} onClick={() => props.onReject(comment)}>退回修改</button></div><label className="feedback-field"><span>修改意见 <small>（退回时必填）</small></span><textarea maxLength={500} value={comment} onChange={(event) => setComment(event.target.value)} /><em>{comment.length} / 500</em></label><footer><span>运行 ID<br /><b>{props.run?.id.slice(0, 12)}</b></span><span>状态<br /><b>{props.run?.status}</b></span></footer></aside></div></div>
}

export function SettingsScreen(props: Navigation & {
  backendUrl: string; agentId: string; agents: AgentProfile[]; humanReview: boolean; connected: boolean
  pingRunning: boolean; pingSteps: PingStep[]; onBackendUrlChange: (value: string) => void; onAgentIdChange: (value: string) => void
  onHumanReviewChange: (value: boolean) => void; onPing: () => void
}) {
  return <div className="app-frame settings-frame"><TitleBar compact connected={props.connected} onBack={() => props.onNavigate('welcome')} /><div className="settings-shell"><aside className="settings-nav"><h1>设置</h1><button className="is-active"><Icon name="code" />服务连接</button></aside><main className="settings-content"><header><h1>服务与数据分析</h1><p>配置 Python 后端、默认 Agent 与人工审核。</p></header><section className="settings-rows"><label><span><b>后端服务地址</b></span><input value={props.backendUrl} onChange={(event) => props.onBackendUrlChange(event.target.value)} /><em><i className={props.connected ? 'is-live' : ''} />{props.connected ? '已连接' : '未连接'}</em></label><label><span><b>默认 Agent</b></span><select value={props.agentId} onChange={(event) => props.onAgentIdChange(event.target.value)}>{props.agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label><label><span><b>人工审核</b><small>启用后，SQL 执行前需要确认。</small></span><button className={`switch ${props.humanReview ? 'is-on' : ''}`} onClick={() => props.onHumanReviewChange(!props.humanReview)}><i /></button></label></section><section className="diagnostics"><h2>连接诊断</h2><p>检查 API 服务和应用状态数据库。</p><div className="ping-card"><div className="ping-card-head"><div><strong>运行健康检查</strong></div><button onClick={props.onPing} disabled={props.pingRunning}>{props.pingRunning ? '测试中…' : '开始测试'}</button></div><div className="ping-timeline">{props.pingSteps.map((step) => <div className="is-complete" key={step.label}><span><Icon name="check" size={13} /></span><strong>{step.label}</strong><small>{step.detail} · {step.duration}</small></div>)}</div></div></section></main></div></div>
}

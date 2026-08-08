import logo from '../assets/brand/logo-horizontal.png'
import mark from '../assets/brand/mark.png'
import type { AppView, Conversation } from '../types'
import { Icon } from './Icon'
import { useState } from 'react'

type TitleBarProps = {
  title?: string
  connected: boolean
  compact?: boolean
  onBack?: () => void
}

export function TitleBar({ title, connected, compact = false, onBack }: TitleBarProps) {
  function windowAction(action: 'minimize' | 'maximize' | 'close') {
    window.ipcRenderer?.send(`window:${action}`)
  }

  return (
    <header className={`titlebar ${compact ? 'titlebar-compact' : ''}`}>
      <div className="traffic-lights">
        <button className="traffic-close" aria-label="关闭窗口" type="button" onClick={() => windowAction('close')} />
        <button className="traffic-minimize" aria-label="最小化窗口" type="button" onClick={() => windowAction('minimize')} />
        <button className="traffic-maximize" aria-label="最大化窗口" type="button" onClick={() => windowAction('maximize')} />
      </div>
      <div className="titlebar-left">
        {onBack ? (
          <button className="titlebar-back" type="button" onClick={onBack}>
            <Icon name="arrow-left" size={17} />
            返回对话
          </button>
        ) : (
          <img className="titlebar-logo" src={logo} alt="DataAgent" />
        )}
      </div>
      <button className="titlebar-center" type="button">
        {title ?? 'DataAgent'}
        {title ? <Icon name="chevron-down" size={13} /> : null}
      </button>
      <div className="titlebar-status">
        <span className={`connection-dot ${connected ? 'is-live' : ''}`} />
        <span>{connected ? '已连接 · 本地环境' : '未连接'}</span>
      </div>
    </header>
  )
}

type SidebarProps = {
  conversations: Conversation[]
  activeConversationId?: string
  collapsed?: boolean
  onNew: () => void
  onNavigate: (view: AppView) => void
  onOpenConversation: (conversation: Conversation) => void
  onRenameConversation: (conversation: Conversation, title: string) => void
  onDeleteConversation: (conversation: Conversation) => void
}

function relativeTime(value: string) {
  const timestamp = value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`
  const elapsed = Date.now() - new Date(timestamp).getTime()
  if (elapsed < 60_000) return '刚刚'
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)} 分钟前`
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)} 小时前`
  return new Date(value).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

export function Sidebar({ conversations, activeConversationId, collapsed = false, onNew, onNavigate, onOpenConversation, onRenameConversation, onDeleteConversation }: SidebarProps) {
  const [search, setSearch] = useState('')
  const visibleConversations = conversations.filter((item) => item.title.toLowerCase().includes(search.trim().toLowerCase()))
  if (collapsed) {
    return (
      <aside className="sidebar sidebar-collapsed">
        <img src={mark} className="sidebar-mark" alt="DataAgent" />
        <button className="square-control" type="button" aria-label="新建分析" onClick={onNew}>
          <Icon name="plus" />
        </button>
        <span className="collapsed-label">对话</span>
        <div className="collapsed-threads">
          {visibleConversations.slice(0, 7).map((item) => (
            <button key={item.id} className={item.id === activeConversationId ? 'is-active' : ''} title={item.title} type="button" onClick={() => onOpenConversation(item)}>
              <span />
            </button>
          ))}
        </div>
        <button className="sidebar-bottom-icon" type="button" aria-label="设置" onClick={() => onNavigate('settings')}>
          <Icon name="settings" />
        </button>
      </aside>
    )
  }

  return (
    <aside className="sidebar">
      <button className="new-analysis" type="button" onClick={onNew}>
        <Icon name="plus" size={19} />
        新建分析
      </button>

      <label className="sidebar-search">
        <Icon name="search" size={17} />
        <input aria-label="搜索会话" placeholder="搜索会话" value={search} onChange={(event) => setSearch(event.target.value)} />
        <kbd>⌘K</kbd>
      </label>

      <nav className="conversation-nav" aria-label="历史会话">
        <section className="conversation-group">
            <div className="conversation-group-title">
              <span>历史会话</span>
              <Icon name="chevron-down" size={13} />
            </div>
            {visibleConversations.map((item) => (
              <div className={`conversation-row ${item.id === activeConversationId ? 'is-active' : ''}`} key={item.id}>
                <button className="conversation-open" type="button" onClick={() => onOpenConversation(item)}><span className="conversation-title">{item.title}</span><span className="conversation-time">{relativeTime(item.updatedAt)}</span></button>
                <button className="conversation-action" aria-label={`重命名 ${item.title}`} type="button" onClick={() => { const title = window.prompt('重命名会话', item.title)?.trim(); if (title) void onRenameConversation(item, title) }}>✎</button>
                <button className="conversation-action" aria-label={`删除 ${item.title}`} type="button" onClick={() => void onDeleteConversation(item)}>×</button>
              </div>
            ))}
            {!visibleConversations.length ? <p className="conversation-time">{search ? '没有匹配的会话' : '还没有分析记录'}</p> : null}
          </section>
      </nav>

      <div className="sidebar-footer">
        <button type="button">
          <Icon name="database" />
          <span>数据源</span>
          <Icon name="chevron-right" size={14} />
        </button>
        <button type="button" onClick={() => onNavigate('settings')}>
          <Icon name="settings" />
          <span>设置</span>
          <Icon name="chevron-right" size={14} />
        </button>
      </div>
    </aside>
  )
}

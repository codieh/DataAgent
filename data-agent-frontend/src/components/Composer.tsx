import { useRef } from 'react'
import { Icon } from './Icon'

type ComposerProps = {
  value: string
  running?: boolean
  compact?: boolean
  placeholder?: string
  onChange: (value: string) => void
  onSubmit: () => void
  onStop?: () => void
}

export function Composer({
  value,
  running = false,
  compact = false,
  placeholder = '询问你的数据…',
  onChange,
  onSubmit,
  onStop,
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null)

  function submit() {
    if (running) {
      onStop?.()
      return
    }
    onSubmit()
  }

  return (
    <div className={`composer ${compact ? 'composer-compact' : ''} ${running ? 'is-running' : ''}`}>
      <textarea
        ref={ref}
        aria-label="向 DataAgent 提问"
        placeholder={placeholder}
        rows={compact ? 1 : 2}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            submit()
          }
        }}
      />
      <div className="composer-tools">
        <button className="icon-control" type="button" aria-label="添加附件">
          <Icon name="attach" size={20} />
        </button>
        <button className="source-select" type="button">
          <Icon name="database" size={16} />
          销售数据库
          <Icon name="chevron-down" size={13} />
        </button>
        {running ? <span className="composer-running-label">停止生成</span> : null}
        <button
          className={`composer-submit ${running ? 'composer-stop' : ''}`}
          type="button"
          aria-label={running ? '停止生成' : '发送'}
          onClick={submit}
        >
          <Icon name={running ? 'stop' : 'send'} size={running ? 16 : 21} />
        </button>
      </div>
    </div>
  )
}

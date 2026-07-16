// ============================================================================
// Composer.tsx —— 一个「输入框 + 发送按钮」的组件
// ----------------------------------------------------------------------------
// 这是学习 React 最好的起点，因为它只有 70 行，却包含了 React 的全部基础：
//   1) 函数组件：一个返回 JSX（界面描述）的普通函数
//   2) Props：父组件传给它的「参数」，决定它长什么样、点了干嘛
//   3) useRef：拿到真实 DOM 元素（这里是 <textarea>）的引用
//   4) 事件处理：onChange / onKeyDown / onClick
//
// 阅读顺序建议：先看最下面的 return(界面长啥样)，
//              再看顶部 ComposerProps(它能接收哪些参数)，
//              最后看中间的 submit(点了会发生什么)。
// ============================================================================

// `useRef` 是 React 的 Hook 之一，用来「抓住」一个 DOM 元素。
// 在这里我们想拿到 <textarea> 这个真实的输入框，所以要导入它。
import { useRef } from 'react'
import { Icon } from './Icon'

// Props = 组件的「入参」。父组件 <App> 在用它时会传这些值进来。
// 语法：`字段名: 类型`，`?:` 表示这个参数可选（不传也行，有默认值）。
// 例如 `running?: boolean` 表示「是否正在运行」，不传默认是下面函数里的 false。
type ComposerProps = {
  value: string                                   // 输入框当前文字（由父组件用 useState 管理）
  running?: boolean                               // 是否正在生成中（决定按钮显示「发送」还是「停止」）
  compact?: boolean                              // 是否紧凑模式（行数不同）
  placeholder?: string                           // 输入框里的灰色提示文字
  onChange: (value: string) => void             // 文字变化时调用的回调（父组件用来存新值）
  onSubmit: () => void                           // 点发送时调用的回调
  onStop?: () => void                            // 点停止时调用的回调（可选）
}

// 组件本体：一个函数，名字首字母大写（Composer）是 React 组件的命名约定。
// 参数解构：`{ value, running = false, ... }` 把 Props 拆出来用，
// `running = false` 表示如果父组件没传 running，就当作 false。
export function Composer({
  value,
  running = false,
  compact = false,
  placeholder = '询问你的数据…',
  onChange,
  onSubmit,
  onStop,
}: ComposerProps) {
  // useRef<HTMLTextAreaElement>(null)：
  //   - 泛型 <HTMLTextAreaElement> 告诉 TS「这个 ref 指向一个 textarea」
  //   - 初始值是 null（还没挂到 DOM 上）
  //   - 之后把 ref={ref} 绑到 <textarea>，React 会自动把元素塞进 ref.current
  const ref = useRef<HTMLTextAreaElement>(null)

  // 内部函数：根据「是否正在运行」决定点击按钮的行为。
  // 这叫「受控组件」思路：按钮本身不存状态，状态(value/running)都在父组件，
  // 组件只是把用户操作「上报」给父组件的回调(onSubmit / onStop)。
  function submit() {
    if (running) {
      onStop?.()   // `?.` 表示「如果 onStop 存在才调用」，避免没传时报错
      return
    }
    onSubmit()
  }

  // return 里写的就是「界面长什么样」——这种写法叫 JSX（像 HTML 的 JavaScript）。
  // 关键点：
  //   - {变量} 里可以塞 JavaScript 表达式，比如 `${compact ? 'a' : 'b'}`
  //   - className 就是 HTML 的 class（React 里用 className 避免和 JS 关键字冲突）
  //   - onClick / onChange 等是「事件」，值是函数
  return (
    <div className={`composer ${compact ? 'composer-compact' : ''} ${running ? 'is-running' : ''}`}>
      {/* 多行输入框。value={value} 表示它显示的文字由父组件控制（受控组件） */}
      <textarea
        ref={ref}
        aria-label="向 DataAgent 提问"
        placeholder={placeholder}
        rows={compact ? 1 : 2}
        value={value}
        onChange={(event) => onChange(event.target.value)}  // 每次输入，把最新文字回报给父组件
        onKeyDown={(event) => {                             // 键盘按下时
          // 按 Enter 且没按 Shift：发送；Shift+Enter 则换行（不拦截）
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()  // 阻止默认的「换行」行为
            submit()
          }
        }}
      />
      <div className="composer-tools">
        {/* 一个纯图标按钮（附件），这里没接功能，是占位演示 */}
        <button className="icon-control" type="button" aria-label="添加附件">
          <Icon name="attach" size={20} />
        </button>
        {/* 数据源选择按钮（占位，固定显示「销售数据库」） */}
        <button className="source-select" type="button">
          <Icon name="database" size={16} />
          销售数据库
          <Icon name="chevron-down" size={13} />
        </button>
        {/* 正在运行时，显示「停止生成」文案 */}
        {running ? <span className="composer-running-label">停止生成</span> : null}
        {/* 主按钮：根据 running 切换图标与样式。点它就调用上面的 submit() */}
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

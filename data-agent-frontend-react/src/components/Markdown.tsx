// ============================================================================
// Markdown.tsx —— 把「markdown 字符串」渲染成「带样式的界面」
// ----------------------------------------------------------------------------
// 背景：React 里写 `{someText}` 会把字符串当作「纯文本」塞进页面，
//       `# 标题`、`**粗体**`、`- 列表` 这些符号不会被翻译成 HTML 标签。
//       要让它们正常显示，需要一个「markdown 解析器」。
//
// 我们用 `react-markdown` 这个库：它会把 markdown 字符串解析成一棵
// 「React 元素树」（不是 dangerouslySetInnerHTML，所以天然防 XSS 注入）。
// `remark-gfm` 是个插件，扩展支持 GitHub 风格的表格、删除线、任务列表。
//
// 用法（任何想渲染 markdown 的地方都可以这样写）：
//   <Markdown>{someMarkdownString}</Markdown>
//
// 学习要点：
//   1) `import ReactMarkdown from 'react-markdown'` —— 默认导出，名字随意
//   2) `<ReactMarkdown>{children}</ReactMarkdown>` —— children 就是 md 文本
//   3) `remarkPlugins={[remarkGfm]}` —— 告诉解析器「顺便启用 Gfm 扩展」
// ============================================================================

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 组件的 Props 类型。`children: string` 表示「只能传一个字符串进来」。
// 这样使用方写 <Markdown>{123}</Markdown> 时 TS 会报错，提早发现问题。
type MarkdownProps = {
  children: string
}

// 一个非常薄的封装：把库包一层，统一加上 Gfm 插件和样式容器。
// `className="markdown-body"` 是约定俗成的命名，对应的样式在 App.css 里。
export function Markdown({ children }: MarkdownProps) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {children}
      </ReactMarkdown>
    </div>
  )
}

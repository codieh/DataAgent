# DataAgent 前端学习导览

> 配套 `data-agent-frontend/src/` 下四份「已加中文注释」的源码阅读。
> 目标读者：零前端基础、想通过本项目学 React + TypeScript 的同学。
> 阅读方式：本文件告诉你「每个概念去哪看、看什么」，代码里的逐行注释负责「这一行到底在干嘛」。

---

## 0. 先把自己装备好

1. **装环境**（一次性）
   - Node.js 18+（本项目已用 22，没问题）
   - 编辑器装 VS Code + 插件 `ESLint`、`Prettier`、`vscode-typescript` 自带
2. **把项目跑起来**
   ```bash
   cd data-agent-frontend
   npm install
   npm run dev        # 启动后是一个桌面窗口（Electron）
   ```
   改任意源码 → 窗口自动热更新，这就是你最重要的「反馈循环」。
3. **先不碰 Electron**：`electron/` 目录是「把网页包成桌面 App 的壳」，
   和 React 学习无关，初期完全忽略。

---

## 1. 概念地图：去哪个文件学什么

| 想搞懂的概念 | 去哪看 | 重点函数 / 位置 |
| --- | --- | --- |
| TypeScript 类型怎么写 | `src/types.ts` | 所有 `type X = ...`；`\|` 联合类型；`?` 可选字段；`Record<string, unknown>` |
| 函数组件长啥样 | `src/components/Composer.tsx` | `export function Composer(...)` |
| Props（组件的输入参数） | `src/components/Composer.tsx` | 顶部的 `ComposerProps` 类型 |
| JSX（界面描述语法） | `src/components/Composer.tsx` | 底部的 `return (...)` |
| 事件绑定（onClick/onChange） | `src/components/Composer.tsx` | `<textarea>` 的 `onChange` / `onKeyDown` |
| `useRef`（抓 DOM / 存不变值） | `src/components/Composer.tsx`、`src/App.tsx` | Composer 里的 `const ref = useRef`；App 里的 `streamRef` |
| `useState`（会触发重画的状态） | `src/App.tsx` | 顶部一连串 `const [x, setX] = useState(...)` |
| `useEffect`（副作用 / 生命周期） | `src/App.tsx` | `useEffect(() => {...}, [backendUrl])` 与 `[]` 两处 |
| `startTransition`（不卡输入的低优先级更新） | `src/App.tsx` | `refreshRun` 里的 `startTransition(() => setRun(...))` |
| `fetch` 封装 + 泛型 `<T>` | `src/api.ts` | `async function request<T>(...)` |
| SSE 流式读取（AI 实时进度） | `src/api.ts` | `consumeRunEvents(...)` 的 `while (true)` 循环 |
| 单页应用：靠 state 切页面 | `src/App.tsx` | 底部 `if (view === 'welcome') ...` |
| 「点一下 → 发请求 → 界面变」完整链路 | `src/App.tsx` | `submit()` 函数（从 116 行附近开始） |

---

## 2. 推荐阅读顺序（由易到难，别跳）

1. **`src/types.ts`** —— 先建立「数据长什么样」的认知。
   不用死记，知道「后端会返回这些结构」即可，后面看到 `Run`、`Conversation` 才不会懵。
2. **`src/components/Composer.tsx`** —— 最小的组件，一口气读完。
   重点体会：组件 = 一个返回 JSX 的函数；Props = 它的参数；它自己不存状态，状态由父组件用 `useState` 管。
3. **`src/api.ts`** —— 学会「前端怎么跟后端要数据」。
   先读 `request<T>()`，再读 `api` 对象里的方法，最后读 `consumeRunEvents` 理解流式。
4. **`src/App.tsx`** —— 压轴大戏，串起前面所有概念。
   按文件内注释标的 ①→⑤ 顺序读：**状态声明 → 拉数据 → 提交链路 → 切页面**。

---

## 3. 动手练习（读 10 遍不如改 1 行）

> 每改完一处，看窗口是否按预期变化；报错就回去读对应注释。

- **【入门】** 在 `Composer.tsx` 的 `placeholder` 默认值里，把 `'询问你的数据…'` 改成你自己的话，看输入框提示文字是否变化。
- **【入门】** 在 `App.tsx` 里，把 `const DEFAULT_BACKEND = 'http://localhost:8000'` 改成一个明显错误的地址，重启 `npm run dev`，观察顶部状态变成「后端连接失败」——理解 `refreshShell` 的 catch 分支。
- **【进阶】** 在 `types.ts` 里给 `AppView` 联合类型加一个 `'about'`，然后在 `App.tsx` 底部加一个 `else if (view === 'about')` 分支，渲染一段「关于本应用」的文字。
- **【进阶】** 在 `Composer.tsx` 里，用 `useRef` + 一个按钮实现「点击清空输入框」（提示：用 `ref.current` 拿到 textarea，调 `.value = ''` 并触发 `onChange`）。
- **【挑战】** 在 `api.ts` 里新增一个接口方法（例如 `api.health` 已存在，仿照它写一个 `api.version`），并在 `App.tsx` 的 `ping()` 里调用它，把版本号显示到设置页。

---

## 4. 两个「仓库原本就有」的 lint 提示（不是你改坏的）

运行 `npm run lint` 可能会看到这两条，它们**在加注释前就存在**，属于项目原有代码，不影响学习：

- `api.ts` 里 `while (true) { ... }` 触发 `no-constant-condition`。
  这是「持续读取 SSE 流」的标准写法，很多项目会为此关掉该规则，可忽略。
- `App.tsx` 里 `useEffect(() => { void refreshShell() }, [backendUrl])` 触发 `react-hooks/exhaustive-deps` 警告。
  这是「只在 backendUrl 变化时刷新」的有意写法，属正常工程取舍。

> 验证方法：本仓库 `git` 历史里的原始版本也会有这两条，注释没有改动任何逻辑。
> 已用 `tsc --noEmit` 确认四份文件类型检查 0 错误。

---

## 5. 下一步学什么（变大牛的路径）

1. 把上面 4 份文件读熟、练习做完。
2. 读 `src/screens.tsx`（5 个页面组件）和 `src/components/AppChrome.tsx`、`Icon.tsx`，看「大组件怎么由小组件拼出来」。
3. 学 CSS：`src/index.css`、`src/App.css` 怎么让界面变好看。
4. 回头看 `README.md` 与 `docs/前端产品需求文档.md`，理解「需求 → 界面」的对应关系。
5. 真正的大牛标志：**能独立给这个 App 加一个小功能**（比如「导出分析结果为 CSV」），并让它跑起来。

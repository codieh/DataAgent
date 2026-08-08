# DataAgent Claude SDK Frontend

这是与 `data-agent-claude-sdk` 配套的 React 前端。它没有复用旧 Java/Python 后端的接口模型，使用新后端的三类边界：

```text
Conversation  -> 历史消息和会话列表
Run           -> 一次分析任务、SSE 事件和工具调用轨迹
ResultSet     -> SQL 结果文件、分页预览和 CSV/JSON 下载
```

## 启动

先启动新后端：

```bash
cd ../data-agent-claude-sdk
uv run uvicorn app.main:app --reload --port 8001
```

再启动前端（桌面客户端开发模式，会拉起 Electron 窗口）：

```bash
npm install
npm run dev
```

`npm run dev` 通过 `vite-plugin-electron` 同时启动 Vite 开发服务器（`http://localhost:5174`）和无边框 Electron 窗口，由主进程 `electron/main.ts` 加载该地址。渲染进程通过 `electron/preload.ts` 暴露的最小 `ipcRenderer` 调用窗口控制（`window:minimize` / `window:maximize` / `window:close`）。

开发时 Vite 会把 `/api` 代理到 `http://localhost:8001`，因此默认不需要填写后端地址。生产桌面端（由 `electron-builder` 打包、走 `file://`）没有该代理，需要在「连接设置」里填写 `VITE_BACKEND_URL` 或后端地址指向独立部署的后端。

也可以通过环境变量配置（参考 `.env.example`）：

```dotenv
VITE_BACKEND_URL=http://localhost:8001
VITE_TENANT_ID=local-tenant
VITE_USER_ID=local-user
```

## 数据流

1. 前端创建或打开 Conversation，并从消息中的 `run_id` 恢复最近一次 Run。
2. 用户提交问题后，前端创建 Run，随后通过带身份请求头的 `fetch` 读取 SSE，而不是使用无法附加自定义 Header 的原生 `EventSource`。
3. SSE 事件按 `seq` 去重。浏览器刷新或重新打开会话时，先读取已持久化事件，再从最后一个序号继续订阅。
4. 工具请求、工具结果、上下文压缩、SQL 执行和最终总结都作为 Run 的事件展示。
5. `sql.executed` 事件只携带 `result_ref` 和统计信息。前端再调用 ResultSet 分页接口读取最多 50 行预览，完整数据通过下载接口获得。

前端只负责展示，不重新实现 Agent Loop、上下文压缩、SQL 安全策略或结果校验；这些能力由 Claude Agent SDK、MCP Tools 和后端应用层负责。

## 验证

```bash
npm run lint
npm run build          # tsc 类型检查 + vite 构建（含 electron/main、preload）+ electron-builder 打包
```

构建产物：渲染进程在 `dist/`，主进程在 `dist-electron/`，安装包输出到 `release/`。

## 安全说明

- 渲染进程默认关闭 `nodeIntegration`、开启 `contextIsolation`，仅通过 `preload` 的 `contextBridge` 暴露最小 API；`electron/main.ts` 不开任何 IPC 透传代理。
- 身份头（`X-Tenant-ID` / `X-User-ID`）由前端注入，后端据此隔离会话与结果。生产环境应由认证网关签发，不要把用户自填 Header 当成鉴权。

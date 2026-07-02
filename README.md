# DataAgent

DataAgent is a desktop-first data analysis agent prototype.

当前版本聚焦于一个可运行的端到端原型：用户在客户端输入问题，后端按多阶段分析流程处理请求，并以流式方式返回中间过程与最终结果。

## Overview

项目当前包含两个核心部分：

- `data-agent-backend`：基于 Spring Boot 的后端服务
- `data-agent-frontend`：基于 Electron + React + TypeScript 的桌面客户端

## What It Can Do

- 类似 Agent / chatbot 的桌面客户端界面
- 后端 `search-lite` 流式分析链路
- 支持展示阶段进度、结构化 payload 和返回结果
- Electron 主进程代理流式请求，避免渲染层直接连接本地 SSE 时不稳定
- 支持作为 DataAgent 后续能力迭代的基础工程骨架

## Project Structure

```text
DataAgent/
├── data-agent-backend/
├── data-agent-frontend/
├── docs/
└── data/
```

## Quick Start

### 1. Start the backend

```bash
cd data-agent-backend
./mvnw spring-boot:run
```

默认后端地址：

```text
http://localhost:8080
```

### 2. Start the frontend

```bash
cd data-agent-frontend
npm install
npm run dev
```

## Current Status

当前仓库仍然偏原型验证阶段，重点在于：

- 打通桌面端与后端的流式交互
- 验证 Agent 风格的数据分析工作流
- 为后续产品化迭代保留基础结构

## Notes

- 如果后端正常但前端收不到流，优先检查 Electron 客户端是否已完整重启。
- 当前打包流程可能受网络环境影响。

## Roadmap

- 优化聊天区的流式展示体验
- 继续完善多阶段分析链路与结果表达
- 补充更完整的项目文档与使用说明

## License

See [LICENSE](./LICENSE).

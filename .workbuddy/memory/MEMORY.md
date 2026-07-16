# DataAgent 项目长期记忆

## 用户背景（2026-07-13 起）
- 用户自述**前端零基础**，希望通过本项目的 `data-agent-frontend` 学习 **React + TypeScript**，目标是成为前端大牛。
- 讲解风格建议：面向初学者，多用类比、从「这行代码在干嘛」入手；默认不使用可视化（除非用户明确要求）。

## 前端教学资料（已生成，可复用）
- 已加中文教学注释的源码（纯注释、逻辑未改，已通过 `tsc --noEmit`）：
  - `data-agent-frontend/src/types.ts`
  - `data-agent-frontend/src/components/Composer.tsx`
  - `data-agent-frontend/src/api.ts`
  - `data-agent-frontend/src/App.tsx`
- 配套学习导览：`docs/frontend-study-guide.md`（概念→文件→函数 映射 + 练习）。
- 注意：`data-agent-frontend` 的 `npm run lint` 原有 1 error(`while(true)`) + 1 warning(useEffect 依赖)，属仓库既有问题，非教学注释引入。

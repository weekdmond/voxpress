# 01 · 架构与项目结构

## 技术栈

| 层 | 选型 | 版本 | 备注 |
|---|---|---|---|
| 构建 | Vite | ^5.0 | ESM、HMR |
| 框架 | React | ^18.3 | 不用 Next，纯 SPA |
| 语言 | TypeScript | ^5.4 | `strict: true` |
| 路由 | TanStack Router | ^1.x | 类型安全、文件路由可选 |
| 状态 | TanStack Query | ^5.x | 服务端状态；本地 UI 状态用 `useState` / `zustand`（可选） |
| 样式 | CSS Modules + CSS 变量 | — | 无 Tailwind，无 CSS-in-JS |
| 图标 | SVG sprite | — | 见 `icons.svg` |
| 字体 | Google Fonts | — | Noto Sans SC、IBM Plex Mono |
| HTTP | `fetch` + 封装 | — | `src/lib/api.ts` |
| SSE | `EventSource` | 浏览器原生 | `src/lib/sse.ts` |

> **为什么不用 Tailwind**：原型的视觉 token 有限（一页 CSS 变量），用 CSS Modules 更清晰；但 `tokens.json` 同样可供 Tailwind 用户使用。

## 目录结构

```
voxpress/
├── public/
│   ├── icons.svg              ← 从 handoff/icons.svg 复制
│   └── favicon.svg
├── src/
│   ├── main.tsx               ← 应用入口
│   ├── App.tsx                ← 顶层路由 outlet
│   ├── router.tsx             ← TanStack Router 定义
│   │
│   ├── layouts/
│   │   └── AppShell.tsx       ← 侧栏 + 主内容 grid
│   │
│   ├── pages/
│   │   ├── Home.tsx
│   │   ├── Library.tsx
│   │   ├── Articles.tsx
│   │   ├── Article.tsx        ← /articles/:id
│   │   ├── Import.tsx         ← /import/:creatorId
│   │   └── Settings.tsx
│   │
│   ├── components/
│   │   ├── primitives/        ← Button, Input, Chip, Avatar, ...
│   │   ├── Sidebar/
│   │   ├── Task/              ← TaskCard, ProgressBar, StageStrip
│   │   ├── ArtCard/
│   │   ├── ArtRow/            ← 列表行（文章、博主、视频）
│   │   ├── Reader/            ← Reader, SourceCard, Drawer
│   │   ├── Stepper/
│   │   └── TweaksPanel/
│   │
│   ├── features/
│   │   ├── tasks/             ← 任务 hooks · SSE 订阅
│   │   ├── creators/
│   │   ├── articles/
│   │   └── settings/
│   │
│   ├── lib/
│   │   ├── api.ts             ← fetch 封装 + 类型
│   │   ├── sse.ts             ← EventSource 封装
│   │   ├── format.ts          ← 数字格式化（w/k）
│   │   └── gradients.ts       ← 确定性头像/缩略图渐变
│   │
│   ├── hooks/
│   │   ├── useDensity.ts
│   │   ├── useTweaks.ts
│   │   └── usePersistedState.ts
│   │
│   ├── styles/
│   │   ├── tokens.css         ← 来自 handoff/tokens.css
│   │   ├── reset.css
│   │   └── globals.css
│   │
│   └── types/
│       ├── api.ts             ← 从 05-api-schema.md 派生
│       └── models.ts          ← 领域模型（Task, Article, Creator）
│
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── .env.example
```

## 路由表

| 路径 | 组件 | 备注 |
|---|---|---|
| `/` | `Home` | 重定向从 `''` 也到这里 |
| `/library` | `Library` | 博主库 |
| `/library/:creatorId` | `Library` | 预留详情，MVP 可先复用列表 |
| `/articles` | `Articles` | 文章列表 |
| `/articles/:id` | `Article` | 阅读器 |
| `/import/:creatorId` | `Import` | 三步导入 |
| `/settings` | `Settings` | |

侧栏的「最近博主」链接：`/library?focus=<creatorId>`（高亮行、不跳详情）。

## 路由持久化

**刷新后要回到原来的页面**。使用 `localStorage.voxpress_nav`，在 Router 初始化时读取，`navigate` 时写入。

## 环境变量

```bash
# .env.example
VITE_API_BASE=http://localhost:8787
VITE_SSE_BASE=http://localhost:8787
VITE_ENABLE_TWEAKS=true
```

## 入口模板

`index.html`：

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>VoxPress</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

## `main.tsx`

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { RouterProvider } from '@tanstack/react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { router } from './router';

import './styles/reset.css';
import './styles/tokens.css';
import './styles/globals.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>
);
```

## 构建与部署

- `pnpm dev` → Vite 5173
- `pnpm build` → 静态产物到 `dist/`
- 部署：把 `dist/` 挂在后端同源（FastAPI `StaticFiles` / Fastify `@fastify/static`），避免 CORS + Cookie 复杂度

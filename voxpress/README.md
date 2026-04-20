# VoxPress

抖音博主内容索引器前端 · 按 `handoff/` 规格 1:1 实现。

## 技术栈

React 18 · TypeScript · Vite 5 · TanStack Router · TanStack Query · CSS Modules · sonner

## 快速开始

```bash
npm install
npm run dev         # 启动开发服务器 (默认使用 mock API)
npm run build       # 构建生产包到 dist/
npm run typecheck   # 仅类型检查
```

## 环境变量

`.env` 已内置默认值,要接真实后端时:

```
VITE_API_BASE=http://localhost:8787
VITE_SSE_BASE=http://localhost:8787
VITE_USE_MOCK=false
```

## 目录

```
src/
├── main.tsx / router.tsx         入口 + 路由
├── layouts/AppShell.tsx          侧栏 + 主区壳
├── pages/                        6 个页面
├── components/
│   ├── primitives/               Button Input Chip Avatar Icon Thumb Box Select ...
│   ├── Sidebar/ Task/ ArtCard/ ArtRow/ Reader/ Stepper/ TweaksPanel/
├── features/tasks/               SSE 订阅 hooks
├── lib/                          api / sse / format / gradients
├── hooks/                        usePersistedState · useDensity
├── styles/                       tokens.css · reset · globals
├── types/api.ts                  API / 领域模型类型
└── mocks/                        mock fixtures + fetch 拦截
```

## Mock 数据

默认 `VITE_USE_MOCK=true`,前端通过拦截 `window.fetch` 来返回虚拟数据并在 SSE 流中推送任务进度。关掉后前端直连 `VITE_API_BASE`。

## 还原度

- 所有颜色 / 间距 / 圆角 / 阴影 / 动画来自 `handoff/tokens.css`
- 18 个 SVG 图标放在 `/public/icons.svg`
- 头像 / 缩略图渐变用 `tokens.json` 里的确定性色板
- 支持 `density-compact` body class + `body.serif` 切换
- Tweaks 协议:`__activate_edit_mode` / `__edit_mode_set_keys` 正常响应

# VoxPress — Frontend Handoff

> 给 Claude Code / Cursor / 人类工程师的开发包。
> 目标：照着这份文档，从零搭出 1:1 还原 `VoxPress v3 (高保真).html` 的 React + Vite 项目。

## 这是什么

你面前的 HTML 原型（`VoxPress v3 (高保真).html`）是完整的视觉与交互基准。本目录把它拆解为：

1. **设计系统** — tokens、组件、图标
2. **页面规格** — 6 个页面的布局、状态、空态、边界
3. **后端契约** — REST + SSE 接口 schema、Postgres 建表 DDL
4. **交互细节** — 导航持久化、Tweaks 协议、密度切换、任务生命周期

## 目录结构

```
handoff/
├── README.md               ← 你正在看
├── 01-architecture.md      ← 项目结构 · 技术栈 · 路由
├── 02-design-tokens.md     ← 颜色/字体/间距/阴影
├── 03-components.md        ← 20+ 个组件的 API
├── 04-pages.md             ← 6 页面规格 + 状态图
├── 05-api-schema.md        ← REST + SSE + 错误码
├── 06-data-models.md       ← Postgres DDL + 关系图
├── 07-interactions.md      ← Tweaks 协议 · 快捷键 · 持久化
├── tokens.css              ← 可直接 @import 的 CSS 变量
├── tokens.json             ← 给 Tailwind / Style Dictionary 用
├── icons.svg               ← SVG sprite（18 个图标）
└── index.html              ← 本目录的导航入口
```

## 推荐打开顺序

### 如果你是 Claude Code / Cursor
1. 先读 `01-architecture.md` 建骨架
2. `tokens.css` + `02-design-tokens.md` 立即接入样式
3. `03-components.md` 从基础组件（Button / Input / Chip）开始落
4. `04-pages.md` 按依赖顺序实现：Layout → Home → Library → Articles → Article → Import → Settings
5. `05-api-schema.md` 先 mock，再接真后端

### 如果你是人类工程师
从 `index.html` 开始，它用同一份视觉系统把所有文档串起来，方便浏览。

## 还原度承诺

- **1:1** — 颜色、间距、字号、圆角、阴影、动画时长全部来自原型
- **字体** — Noto Sans SC + IBM Plex Mono（Google Fonts）
- **图标** — 18 个自绘 SVG（无外部依赖），见 `icons.svg`
- **交互** — 包括 Tweaks 面板协议、`localStorage` 持久化、密度切换

## 技术栈确认

```
React 18 · TypeScript · Vite · TanStack Query · TanStack Router
无 UI 框架（原生组件 + CSS Modules 或 vanilla-extract）
```

如需 Tailwind，`tokens.json` 可直接喂给 `tailwind.config.ts` 的 `theme.extend`。

## 后端假设

- Python FastAPI 或 Node Fastify（任选）
- PostgreSQL 16（已在原型侧栏标注）
- Ollama 本地推理（qwen2.5:72b）
- SSE 推送任务进度
- 单机部署、无需鉴权（MVP 阶段）

详见 `05-api-schema.md`。

## 原始资源

- **高保真原型**：`../VoxPress v3 (高保真).html`
- **v2 线框**：`../VoxPress Wireframes v2 (合并版).html`（可作为低保真参考）

---

**约定**：本文档中的 TypeScript 类型、SQL DDL、CSS 变量均为**可直接复制**的实现代码，不是伪代码。

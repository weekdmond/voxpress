# 07 · 交互细节

## 路由

用 React Router v6。所有路由挂在 `<Shell>` 下（Shell = Sidebar + 主内容器）。

```tsx
<Route element={<Shell />}>
  <Route index element={<HomePage />} />
  <Route path="library" element={<LibraryPage />} />
  <Route path="articles" element={<ArticlesPage />} />
  <Route path="articles/:id" element={<ArticlePage />} />
  <Route path="import/:creatorId" element={<ImportPage />} />
  <Route path="settings" element={<SettingsPage />} />
</Route>
```

- Sidebar 的 active 项用 `useLocation().pathname` 判断前缀
- 面包屑 / 返回按钮用 `navigate(-1)`

## 状态管理

- **服务器状态** → TanStack Query（`@tanstack/react-query`）
- **URL 状态** → useSearchParams（筛选、排序）
- **UI 本地状态** → `useState` / `useReducer`
- **全局设置/主题** → 一个 Zustand store（简单小巧）

不引入 Redux。

## URL 筛选参数约定

| 页面 | 参数 |
|---|---|
| `/library` | `?platform=douyin&verified=1&q=...` |
| `/articles` | `?q=&creator=123&tag=AI&since=30d&cursor=...` |
| `/import/:id` | `?min_dur=180&min_likes=10000&since=30d` |

所有筛选 chip 点击都是修改 URL（不是局部 state），这样页面刷新可恢复。

## 全局交互

### 1. Toast

用 `sonner`：
- primary 操作成功：`toast.success('已重新整理')`
- 错误：`toast.error(err.message)`
- 右下角，自动 4s 消失

### 2. 确认弹窗

删除类操作用 `<AlertDialog>`（shadcn-style）。MVP 可用原生 `confirm()` 占位。

### 3. 快捷键

| 键 | 动作 |
|---|---|
| `⌘K` / `Ctrl K` | 打开全局搜索（可后期实现，先 noop） |
| `/` | 聚焦当前页搜索框 |
| `G H` `G L` `G A` `G S` | 跳首页 / 库 / 文章 / 设置 |
| `Esc` | 关闭 drawer / modal |

用 `react-hotkeys-hook`。

### 4. SSE 连接状态

Sidebar 底部的 chip 随 EventSource readyState：
- `OPEN` → 绿点 + 「本地服务 · 运行中」
- `CONNECTING` → 黄点 + 「连接中」
- `CLOSED` → 红点 + 「已断开，点击重试」

## 组件级交互

### TaskCard

- `stage==='done'` 时，200ms 后 fade-out 并触发 `onComplete(article_id)`，父组件从运行列表移除、插入最近完成
- `status==='failed'` 不自动消失，显示 `error` + 「重试」按钮（`POST /api/tasks` 再来一次）

### ArtRow（列表行）

- 整行可点击 → `navigate()`
- hover：bg 变 `--vp-bg-2`
- 右键：打开上下文菜单（重命名 / 删除 / 复制链接）—— 可以后期做

### Reader

- 「显示原稿」用 React state 控制 `.split` class
- Drawer 动画：`transition: transform 280ms cubic-bezier(.2,.8,.2,1)`，从右侧滑入
- 「重新整理」点击后立刻显示 confirm：「当前文章会被覆盖，确认？」

### Import 批量选择

- `useCheckboxGroup()` hook：返回 `selected: Set<string>`、`toggle`、`toggleAll`、`isAllSelected`
- 底部「开始处理 N 条」按钮跟着 selected.size 联动

## Tweaks 协议实现

根文件 `src/main.tsx` 早于所有组件挂载前：

```ts
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "comfortable",       // "comfortable" | "compact"
  "fontSerif": false,             // 正文是否用 serif
  "accentHue": 210                // HSL hue，210 = 当前钢蓝
}/*EDITMODE-END*/;

const tweaks$ = create(() => ({ ...TWEAK_DEFAULTS }));

window.addEventListener('message', (ev) => {
  if (ev.data?.type === '__activate_edit_mode')   showTweaksPanel();
  if (ev.data?.type === '__deactivate_edit_mode') hideTweaksPanel();
});
window.parent.postMessage({ type: '__edit_mode_available' }, '*');

function setTweak(patch: Partial<typeof TWEAK_DEFAULTS>) {
  tweaks$.setState(patch);
  window.parent.postMessage({ type: '__edit_mode_set_keys', edits: patch }, '*');
}
```

Tweaks 面板（React，固定右下角）：
- density radio → 改 `:root` 上的 `--vp-row-h`
- fontSerif toggle → body class `body.serif` 切换正文字体
- accentHue slider → `--vp-accent: oklch(62% 0.12 <hue>)`

## 加载/空/错状态

每个页面/列表都实现三态：

```tsx
if (isLoading) return <Skeleton />;
if (error)     return <ErrorState retry={refetch} />;
if (!items.length) return <EmptyState illust="..." cta="..." />;
return <List items={items} />;
```

Skeleton 用 `--vp-bg-2` 色块，shimmer 动画（同 ProgressBar 的 shimmer）。

## 无障碍

- 所有 icon button 必须有 `aria-label`
- 表格行 `role="button"` + `tabIndex={0}` + Enter/Space 触发点击
- Reader 里的 `h1/h2` 不要用 `<div>` 模拟
- 对比度：`--vp-ink` 对 `--vp-bg` ≈ 13:1（AAA），`--vp-ink-3` 对 `--vp-bg` ≈ 4.8:1（AA+）

## 性能

- 文章列表 ≥ 100 时，用 `@tanstack/react-virtual`
- Reader 的原稿 drawer lazy mount（`split=true` 时才渲染）
- 图标 sprite 整个文件 < 5KB，用浏览器缓存

## 打包

- Vite + React + TS
- 一次构建：产物分为 `index.html` + 一个 JS bundle + 一个 CSS bundle + `/icons.svg`
- 后端的 Elysia 直接 serve `dist/`

## 环境变量

```env
VITE_API_BASE=http://localhost:8787
VITE_SSE_BASE=http://localhost:8787
```

SSR 不做，MVP 就是 SPA。

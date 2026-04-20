# 04 · 页面规格

每个页面按照：布局 → 数据依赖 → 状态（loading / empty / error）→ 交互 → 边界。

## Page Head 模式（所有页面通用）

```
[H1 页面标题] [mono 说明]         （底部 16px padding + 1px line-2 分隔）
```

- H1：26px / 600 / `-0.02em`
- 说明：mono 11px、`--vp-ink-3`、baseline 对齐 H1

---

## 1. Home (`/`)

**目的**：快速提交新任务 + 查看运行中任务 + 最近完成文章。

### 布局

```
┌ page-head: "首页" · 提交新任务 · 运行中 · 最近完成
│
├ 大输入框（radius 10、h 56、download 图标 + URL input + 提交按钮）
│  └ annot: "单一输入框自动识别三种 URL · 回车或点提交均可"
│
├ 运行中任务
│  ├ header: H3 "运行中任务" + live chip "N running" / mono "SSE · 实时推送"
│  └ TaskCard × N
│
├ 分隔线
│
└ 最近完成
   ├ header: H3 "最近完成" / "全部 138 篇 →"
   └ grid-3 × ArtCard（最多 6 张）
```

### 数据

- `useRunningTasks()` → SSE stream of tasks with status !== 'done'
- `useRecentArticles({ limit: 6 })` → REST

### URL 识别（前端）

```ts
function detectUrlKind(url: string): 'short' | 'video' | 'user' | 'unknown' | null {
  if (!url) return null;
  if (/v\.douyin\.com/.test(url)) return 'short';
  if (/douyin\.com\/video\//.test(url)) return 'video';
  if (/douyin\.com\/user\//.test(url)) return 'user';
  return 'unknown';
}
```

### 提交行为

| URL 类型 | 行为 |
|---|---|
| `user`（博主主页） | 前端先 `POST /api/creators/resolve`，拿到 creator id，跳 `/import/:id` |
| `video` / `short` | `POST /api/tasks` 创建任务，输入框清空，新任务 prepend 到运行列表，SSE 会自动推进 |
| 空 | 按钮置灰（MVP 也可以走一个 demo task） |
| `unknown` | Input 下方红字提示「不支持的链接」 |

### 空态

- 运行中任务为空 → 仍显示 header，下方显示 mono 一行「暂无运行中任务」
- 最近完成为空（新装机）→ 卡片网格换成一个 box：「从粘贴链接开始 →」按钮聚焦输入框

### 边界

- 任务列表超过 5 条时，只显示前 5 条 + 「还有 N 个任务（全部 →）」
- 页面刷新时，SSE 重新连接，运行中任务从 `GET /api/tasks?status=running` 先拉一次快照再订阅

---

## 2. Library (`/library`)

**目的**：管理已导入的博主。

### 布局

```
┌ page-head: "博主库" · mono "12 位博主 · 按粉丝排序"
│
├ filter row: [solid chip "全部·12"] [chip "抖音ˇ"] [chip "蓝V·4"] ... [search input w:280] [primary "导入博主"]
│
└ 表格（box 嵌列表行）
   ├ art-head: 博主 / 粉丝 ↓ / 文章 / 获赞 / 最近更新 / 认证
   └ art-row × N：头像(sm) + 名字/handle/region/bio 两行 · 数字 · 文字 · ✓/–
```

### 列宽（flex 比例）

```
博主:2   粉丝:1   文章:0.7   获赞:1   最近:1   认证:0.6
```

### 数据

- `useCreators({ sort: 'followers:desc' })`

### 交互

- 点击行 → 进入博主详情（MVP 可先做一个 modal 或 `/library/:id` 列当期文章 + 「导入新视频」按钮）
- 「导入博主」按钮 → 打开 modal 输入博主主页 URL → 走 `resolve` → 跳 `/import/:id`

### 空态

首次打开（0 博主）：全居中空态，icon `users` + 标题 + 「导入第一个博主」primary 按钮。

---

## 3. Articles (`/articles`)

**目的**：所有已整理文章列表。

### 布局

同 Library，但表格列不同：

```
filter chips: [solid "138 篇"] [博主ˇ] [标签ˇ] [近 30 天] ... [search w:280]

art-head: 标题 / 博主 / 标签 / 字数 / 点赞 / 日期 ↓
art-row × N: [thumb 36×24] title | avatar(xs) + 名 | #tag #tag | 2,146 | 4.5w | 今天
```

### 列宽

```
标题:2.4   博主:1.1   标签:1   字数:0.7   点赞:0.8   日期:0.9
```

### 数据

- `useArticles({ cursor, filter })` with infinite scroll
- 搜索：300ms debounce → `?q=...`

### 交互

- 点行 → `navigate('/articles/:id')`
- 筛选 chip 点击 → 打开下拉多选

### 空态

「138 篇」为 0 时：展示引导语 + 指向首页的 CTA。

---

## 4. Article (`/articles/:id`)

**目的**：沉浸阅读、比对原稿、导出。

### 布局

```
page-head 是 mini breadcrumb：← 文章列表 / <创作者名>

Reader 容器（radius 10、shadow-md）:
  ┌ Toolbar:
  │   [avatar sm][名字/时长meta]         [显示原稿] [重新整理] [导出 .md] [标签]
  │
  └ Body（grid，可 split 2 列）:
     ├ Article 区:
     │   h1 + 摘要(italic+left border)
     │   SourceCard（结构化来源）
     │   正文（h2 + p + blockquote）
     │
     └ Drawer（split 时显示，380px）:
         chip "原始逐字稿" + mono "whisper large-v3"
         SegBlock × N（timestamp + 文本）
```

### 数据

- `useArticle(id)` → 文章主体 + source + segments
- 正文用 `dangerouslySetInnerHTML`（来自服务器 sanitized HTML），或用 markdown 渲染器（推荐 `marked` + `DOMPurify`）

### 交互

| 动作 | 行为 |
|---|---|
| 「显示/隐藏原稿」 | toggle `split` class，drawer 淡入 |
| 「重新整理」 | `POST /api/articles/:id/rebuild` → 显示 toast、加新任务 |
| 「导出 .md」 | `GET /api/articles/:id/export.md`，触发下载 |
| 「标签」 | 打开 popover 编辑标签 |
| 点击 drawer 段 | 高亮 + 跳到 article 对应段（MVP 可先不做段映射） |

### 边界

- Article 区 padding：`48 72 64 72`
- 窗口宽度 < 1100 时，drawer 自动合上
- Reader-aside 的 `max-height: calc(100vh - 180px)` + 自己滚动（内容不跟主文一起滚）

---

## 5. Import (`/import/:creatorId`)

**目的**：从博主主页导入 N 个视频、批量创建任务。

### 布局

```
page-head: "博主批量导入" · "<博主名> · N 条视频"

3-step Stepper（STEP 1 ✓粘贴 | STEP 2 选择 | STEP 3 开始）

Creator Summary Box:
  [avatar lg] [名+蓝V chip + handle/region]  [125.4w粉 / 48作品 / 1,203w获赞 mono stats]

Filter + Action Row:
  [solid "选中 N / total"] [chip 时长>3min] [chip 近30天] [chip 点赞>1w]
  ...
  [primary "开始处理 <N> 条 →"]

视频表格:
  art-head: [checkbox] 视频 / 时长 / 点赞 / 播放 / 发布
  art-row × N: [checkbox][Thumb 52×34 + play icon] title · dur · likes · plays · date
```

### 数据

- `useCreator(creatorId)` + `useCreatorVideos(creatorId, filter)`
- 默认筛选：近 30 天 + 点赞 > 1w

### 交互

- 顶部「选中 N / total」与底部按钮的 N 联动
- 全选 checkbox 在表头左侧
- 「开始处理」→ `POST /api/tasks/batch { video_ids: [...] }` → 跳回 `/`

### 空态

博主没视频或全被过滤 → 把 stat box 下方改为 empty-state「换一个筛选条件」。

### Stepper 状态

| 步骤 | 条件 |
|---|---|
| STEP 1 done | 总是（已经 resolve 到 creator） |
| STEP 2 active | 进入页面默认 |
| STEP 3 active | 点击按钮后、跳转前的 spinner 态 |

---

## 6. Settings (`/settings`)

**目的**：MVP 配置，同步到后端 config。

### 布局

每段配置用一个 Box，共 5 段（纵向 stack，间距 20）：

1. **LLM 后端**
   - 后端选择（Ollama / Claude 预留）
   - 模型选择（从 `/api/tags` 动态加载）
   - 并发数（数字输入）
2. **Whisper 转写**
   - 模型（large-v3 / medium / small）
   - 语言（强制中文 / 自动）
3. **Prompt 模板** — textarea + 恢复默认 / 保存
4. **抖音 Cookie** — 文件上传 / 粘贴 / 测试连接 + warn chip「未导入」
5. **存储** — 音频保留天数

### 每 Box 的 head 结构

```
Row between:
  Col:
    <b style="font-size:14">段标题</b>
    <span color:ink-3 size:11.5>描述</span>
  Chip（状态：ok / warn / default）
Divider
Field × N
```

### Field 组件

```tsx
<div class="field">
  <label>标签（160px）</label>
  <div class="ctl">
    <select class="sel">...</select>
    <div class="help">提示文字</div>
  </div>
</div>
```

### 数据

- `useSettings()` → GET 全部 config
- `updateSettings(patch)` → PATCH，乐观更新

### 交互

- Prompt textarea 改动时 → 「保存」变 primary 激活
- 「测试连接」 → `POST /api/cookie/test`，返回成功/失败 toast

---

## 路由持久化

见 `07-interactions.md`。

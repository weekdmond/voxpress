# 02 · 设计 Tokens

> **机器可读**：同目录下 `tokens.css`（直接 `@import`）和 `tokens.json`（Tailwind / Style Dictionary）。
> **本文档**：讲语义、使用场景、排除项。

## 颜色

### 中性（背景 & 墨色）

| Token | 值 | 用途 |
|---|---|---|
| `--vp-bg` | `#f4f5f7` | 应用背景（冷灰） |
| `--vp-bg-2` | `#eceef2` | 次级背景：表头、hover 填充、soft chip |
| `--vp-panel` | `#ffffff` | 卡片、侧栏、输入框、reader 正文背景 |
| `--vp-ink` | `#0f1419` | 主正文、大标题 |
| `--vp-ink-2` | `#3d4550` | 次级正文、按钮标签 |
| `--vp-ink-3` | `#7b8594` | 第三级文字、图标、mono 元数据 |
| `--vp-ink-4` | `#b6bdc8` | placeholder、禁用态、箭头辅助符 |

### 描边

| Token | 值 | 用途 |
|---|---|---|
| `--vp-line` | `#e2e5eb` | 默认边框（卡片、输入） |
| `--vp-line-2` | `#eef0f4` | 分割线、reader 内部 |
| `--vp-line-strong` | `#d0d5de` | hover 边框、subtle 强调 |

### Accent（冷色 slate）

| Token | 值 | 用途 |
|---|---|---|
| `--vp-accent` | `#4f5d75` | 进度条、行内强调、focus ring 中层 |
| `--vp-accent-2` | `#2d3748` | **主按钮底色、激活侧栏项底色** |
| `--vp-accent-soft` | `#eef1f6` | focus ring 外层、blockquote 底色、chip 背景 |
| `--vp-accent-tint` | `#dde3ec` | chip 边框、hover 态 |

> **规则**：Accent 是系统唯一的品牌色。**不要引入绿、红、紫作为 accent**。语义色仅用于状态。

### 语义

| Token | 值 | 用途 |
|---|---|---|
| `--vp-ok` / `--vp-ok-soft` | `#4a7c59` / `#e8efe9` | 成功、已连接、已导入；live 脉冲点 |
| `--vp-warn` / `--vp-warn-soft` | `#9c6f1e` / `#f6efdf` | 未导入 Cookie、待确认 |
| `--vp-danger` | `#9c4a4a` | 删除、错误（但不做底色，仅做文字/边框） |

## 字体

```
Sans: Noto Sans SC  400/500/600/700
Mono: IBM Plex Mono 400/500
Serif: Instrument Serif（保留，暂未使用）
```

### 规则

- **所有中文正文用 Sans**
- **所有数字、URL、代码、时间戳用 Mono** + `font-variant-numeric: tabular-nums`
- **统计数字**（125.4w、48 条）用 Mono，数量级越大字号越大
- Letter-spacing：H1/H2 用 `-0.015em ~ -0.025em`，正文不用

### Type scale

| 语义 | Size | Weight | Line-height |
|---|---|---|---|
| `page-title` (H1) | 26 | 600 | 1.1 |
| `article-h1`（reader） | 32 | 700 | 1.2 |
| `section-title` (H3) | 14 | 600 | 1.3 |
| `article-h2` | 19 | 600 | 1.3 |
| `body` | 13.5 | 400 | 1.55 |
| `reader-body` | 15.5 | 400 | 1.8 |
| `meta` (mono) | 10.5–11 | 400 | 1.4 |

## 间距

4-based scale。常用：`12 / 14 / 18 / 24 / 40`。
- 卡片内 padding：`18px`（紧凑 `14px`）
- 卡片之间：`14px`（紧凑 `10px`）
- 页面 padding：`28px 40px 80px`
- Reader 内容 padding：`48px 72px 64px`

## 圆角

| Level | Value | 用途 |
|---|---|---|
| sm | 4 | 内联小控件、tag、thumb |
| base | 6 | 按钮、输入、chip（非胶囊） |
| md | 8 | 卡片、task、box |
| lg | 10 | 大输入（首页提交框）、reader 容器、tweaks panel |
| xl | 12 | 大头像（lg avatar）、特殊卡片 |
| full | 999 | chip 胶囊、头像、进度条 |

## 阴影

| Level | 用途 |
|---|---|
| `sm` | 默认卡片、按钮、输入、task |
| `md` | hover 态提升、reader 容器、primary 按钮 |
| `lg` | Tweaks 浮层、模态 |

## 渐变

### 头像渐变（9 色轮换）
按 creator ID 确定取 `avatarGradients[id % 9]`。**永不随机**——同一个博主在任何地方同色。

### 缩略图渐变（5 色轮换）
按文章/视频在列表中的位置（index % 5）。低饱和度、冷偏暖的中性色，搭配 `radial-gradient` 白光高光。

详见 `tokens.json` → `avatarGradients` / `thumbGradients`。

## 动画

| Token | Duration | 用途 |
|---|---|---|
| fast | 120ms | hover 状态变色 |
| normal | 150ms | focus ring、transform |
| slow | 400ms | 进度条宽度 |

- Easing：全局 `cubic-bezier(0.4, 0, 0.2, 1)`
- **Pulse**（live chip 绿点）：1.8s ease-in-out infinite，opacity 1 → 0.35 → 1
- **Shimmer**（进度条光带）：1.6s linear infinite，左右穿过

## 不要这样做

- ❌ 不要用真实的照片/emoji 当头像 → 用确定性渐变 + 首字
- ❌ 不要引入新的 accent hue（除非走 Tweaks 临时试色）
- ❌ 不要用 `box-shadow` 做扁平风格的虚假描边 → 用 `border` + `--vp-line`
- ❌ 不要用非 tabular-nums 的字体渲染数字
- ❌ 不要在中文正文里混用 Inter（会破坏字形节奏）

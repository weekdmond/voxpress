# 03 · 组件清单

所有组件用 **CSS Modules**。文件放在 `src/components/<Name>/<Name>.tsx` + `<Name>.module.css`。

## 基础原件 (`primitives/`)

### `<Button variant size>`
```tsx
type ButtonProps = {
  variant?: 'default' | 'primary' | 'ghost';
  size?: 'sm' | 'md';
  icon?: React.ReactNode;   // leading SVG <Icon name="..." />
  trailing?: React.ReactNode;
  children: React.ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>;
```
- `default`：白底、`--vp-line` 边框、hover `--vp-bg-2`
- `primary`：`--vp-accent-2` 底、白字、带 `--vp-shadow-sm`；hover 变 `#1a222e`
- `ghost`：无边框、无背景；hover `--vp-bg-2`
- `sm`：padding `4px 9px`, font 11.5
- `md`（默认）：padding `7px 13px`, font 12.5

### `<Input size leading trailing>`
```tsx
type InputProps = {
  size?: 'md' | 'lg';     // lg = 56px, radius 10
  leading?: ReactNode;    // e.g. <Icon name="search" />
  trailing?: ReactNode;   // e.g. <Button />
  mono?: boolean;
} & InputHTMLAttributes<HTMLInputElement>;
```
- 高度 38（md）/ 56（lg）
- Focus：`border --vp-accent`，`box-shadow 0 0 0 3px --vp-accent-soft`
- `lg` 版内部 input 用 mono 字体（URL 场景）

### `<Chip variant>`
```tsx
type ChipProps = {
  variant?: 'default' | 'solid' | 'accent' | 'ok' | 'warn';
  live?: boolean;   // 加脉冲绿点
  icon?: ReactNode;
  children: ReactNode;
};
```
胶囊形，`border-radius: 999px`。

### `<Avatar size id>`
```tsx
type AvatarProps = {
  size?: 'xs' | 'sm' | 'md' | 'lg';  // 18 / 24 / 32 / 52
  id: number;        // creator id → 决定渐变色
  initial: string;   // 首字
};
```
大小/圆角表（`lg` 用 12px 圆角方形，其它圆形）：

| size | box | radius | font |
|---|---|---|---|
| xs | 18 | 50% | 8.5 |
| sm | 24 | 50% | 10 |
| md | 32 | 50% | 12 |
| lg | 52 | 12 | 18 |

渐变来自 `lib/gradients.ts`：
```ts
import gradients from '@/tokens.json';
export const avatarGradient = (id: number) =>
  gradients.avatarGradients[id % gradients.avatarGradients.length];
```

### `<Icon name size>`
```tsx
type IconProps = { name: IconName; size?: number };
// IconName: 'home' | 'users' | 'doc' | 'cog' | 'search' | 'arrow-right' | ...
```
实现：
```tsx
export const Icon = ({ name, size = 14 }: IconProps) => (
  <svg width={size} height={size} aria-hidden>
    <use href={`/icons.svg#i-${name}`} />
  </svg>
);
```

### `<Box variant>` / `<Row>` / `<Col>`
简单的 layout 原子。`<Box>` = 有边框白底；`variant="soft"` 用 `--vp-bg-2`、无边框；`variant="lifted"` 用 `shadow-md`。

### `<Divider />` — 1px `--vp-line-2`

### `<Thumb w h seed>`
缩略图占位。`seed` 决定渐变色：
```tsx
export const Thumb = ({ seed, w, h, play }: { seed: number; w: number; h: number; play?: boolean }) => {
  const g = thumbGradients[seed % thumbGradients.length];
  return (
    <div className={s.thumb} style={{ width: w, height: h, background: g }}>
      {play && <Icon name="play" size={14} />}
    </div>
  );
};
```

## 复合组件

### `<Sidebar>`
props 无（内部用路由 hook）。包含：brand、4 个主导航（home/library/articles/settings）、最近博主列表、底部状态块。
- 宽 232，`position: sticky; top: 0; height: 100vh`
- active 项用 `--vp-accent-2` 底 + 白字
- 每项末尾可选 count chip

### `<TaskCard task>`
```tsx
type Task = {
  id: string;
  title: string;
  creator: { id: number; name: string; initial: string };
  stage: 'download' | 'transcribe' | 'organize' | 'done' | 'error';
  progress: number;         // 0–100
  eta?: string;             // "~4:32 剩余"
  detail?: string;          // "mlx-whisper large-v3"
};
```
结构：title-row + StageStrip + ProgressBar

### `<StageStrip stages current>`
4 段 pill，完成用 `--vp-ok-soft` / 当前用 `--vp-accent-2` / 未到用 `--vp-bg-2`。顺序：下载 → 转写 → 整理 → 保存。

### `<ProgressBar value active accent>`
高 4px。`active=true` 时加 shimmer 动画层。`accent` 时用线性渐变。

### `<ArtCard article>` — 最近完成卡片
- 头像（xs）+ mono meta
- 2 行标题（`-webkit-line-clamp: 2`）
- 底部 meta：字数 / ♥ 数 / 2 个标签
- Hover 抬升 1px + `shadow-md`

### `<ArtRow>`
通用列表行，多种用法：文章列表行、博主行、导入视频行。用 `children` 组合而不是配置 props：
```tsx
<ArtRow onClick={...}>
  <ArtRow.T flex={2.4}><Thumb .../><span>{title}</span></ArtRow.T>
  <ArtRow.C flex={1.1}><Avatar .../><span>{creator}</span></ArtRow.C>
  <ArtRow.Tag>{tags}</ArtRow.Tag>
  <ArtRow.Num flex={0.7}>{words}</ArtRow.Num>
</ArtRow>
```

### `<Reader article>`
容器：radius 10、shadow-md、overflow-hidden。包含：
- `<ReaderToolbar>`：左头像+创作者+时间；右侧 4 个按钮（显示原稿 / 重新整理 / 导出 / 标签）
- `<ReaderBody split>`：`split=true` 时右侧 380px drawer
- `<ReaderArticle>`：padding `48/72/64`，内置 `h1`/`sum`/`h2`/`p`/`blockquote` 样式
- `<SourceCard>`：两列 grid，灰底，Mono 字，结构化键值对
- `<Drawer segments>`：逐字稿分段，accent 色时间戳

### `<Stepper steps current>`
3 列 grid。每步：圆形数字徽章（完成用 ok 绿 + check 图标，当前用 accent-2，待做用 bg-2）+ 标签组。

### `<Box>` 设置区
每段设置用一个大 box：
```
<Box>
  <Row between>
    <Col><b>标题</b><sub>描述</sub></Col>
    <Chip ok>状态</Chip>
  </Row>
  <Divider />
  <Field label="后端"><Select .../></Field>
  <Field label="模型"><Select .../><Help>...</Help></Field>
</Box>
```

### `<Select>` / `<Textarea>`
自定义样式见 `tokens.css` 里的 `select.sel` / `textarea.ta`，在 React 里包一层即可。

### `<TweaksPanel>`
- 默认 hidden
- 收到 `postMessage({ type: '__activate_edit_mode' })` 时 open
- 详细协议见 `07-interactions.md`

## 图标清单

`/public/icons.svg` 提供 18 个：

`home · users · doc · cog · search · arrow-right · arrow-left · download · wave · sparkle · check · play · heart · swap · refresh · tag · external · chevron`

全部 `stroke="currentColor"` + `stroke-width="1.8"`（除 check=2.2、play=fill、wave=round cap）。

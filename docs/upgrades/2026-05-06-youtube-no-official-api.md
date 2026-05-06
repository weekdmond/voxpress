# 2026-05-06 YouTube No Official API Support

## Status

In Progress

## Context

SpeechFolio 当前以抖音内容导入、博主同步、音频转写和文章生成为主。产品希望扩展到 YouTube，但暂不依赖 YouTube Data API v3、OAuth 或官方 captions API。

无官方 API 方案可以降低接入门槛，避免 API key、配额和 OAuth 审核成本；代价是元数据完整性、稳定性和合规边界都弱于官方 API 方案。本工具按个人本地工具定位处理：不设计 OAuth 或第三方授权流程，但仍需要把字幕、音频下载和 ASR 转写做成可配置能力，方便在不同运行环境下关闭或降级。

## Goals

- 支持导入 YouTube 单条视频链接，形成 `Video`、`Creator` 和任务上下文。
- 支持导入 YouTube 频道或 `@handle`，同步最近公开视频到博主列表。
- 不使用 YouTube Data API key。
- 保留当前 SpeechFolio 的博主、视频、任务、文章生成工作流。
- 默认链路在无法获取字幕或音频时仍能展示视频卡片和 iframe 播放入口。

## Non-Goals

- 不承诺拉取频道历史全量视频。
- 不承诺获取播放量、点赞、评论数等完整统计。
- 不设计 YouTube OAuth、官方字幕权限校验或多租户授权流程。
- 不绕过登录、年龄限制、地区限制、付费限制或平台反自动化限制。
- 不把 YouTube 内部 Web 接口作为长期稳定依赖。

## Decision

采用两层能力模型：

1. **基础层：RSS + oEmbed**
   - 频道最近视频使用 YouTube RSS feed：`https://www.youtube.com/feeds/videos.xml?channel_id=UC...`。
   - 单条视频基础信息使用 oEmbed：`https://www.youtube.com/oembed?url=...&format=json`。
   - 该层不需要 API key，适合默认启用。
   - 可获得标题、作者、缩略图、嵌入 HTML、发布时间等基础信息；通常无法获得时长、播放量、点赞、评论数。

2. **增强层：yt-dlp metadata / subtitles**
   - 使用 `yt-dlp` 获取单条视频或频道列表的补充元数据。
   - 优先尝试公开视频字幕和自动字幕，而不是直接下载音频。
   - 失败时降级到基础层，不让导入完全失败。
   - 该层需要限流、缓存、错误翻译和显式产品提示。

增强层同时负责字幕和音频处理：

- 优先获取公开视频字幕或自动字幕，成功时直接进入 transcript、纠错和文章生成。
- 没有字幕时，抽取音频并复用现有 DashScope ASR、纠错和文章生成管线。
- 提供全局配置开关，允许部署时关闭 YouTube 音频下载或仅保留字幕处理。

## Data Model

现有 `creators.platform` 已支持多平台扩展，但 `videos.id` 当前是全局主键。为避免跨平台 ID 冲突，建议二选一：

- 短期方案：YouTube 视频 ID 入库为 `youtube:{video_id}`，`source_url` 保存原始链接。
- 长期方案：新增 `videos.platform`、`videos.external_id`，并改成唯一约束 `(platform, external_id)`；内部主键继续使用现有 `id` 或迁移到独立 surrogate id。

建议新增或规范化以下字段：

- `creators.platform = "youtube"`
- `creators.external_id = channel_id`
- `creators.handle = @handle`，如果无法解析则使用 `@{channel_id}`
- `videos.source_url = canonical YouTube URL`
- `videos.cover_url = thumbnail URL`
- `videos.duration_sec = 0` 表示基础层未知时长
- `videos.likes/comments/shares/collects = 0` 表示未知或不可得，不作为真实 0 曝露给用户

前端展示时应将未知统计显示为 `—`，避免把缺失值误读为真实数据。

## URL Handling

需要新增 YouTube URL resolver，识别以下输入：

- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/shorts/VIDEO_ID`
- `https://www.youtube.com/embed/VIDEO_ID`
- `https://www.youtube.com/@handle`
- `https://www.youtube.com/channel/UC...`
- `https://www.youtube.com/playlist?list=...`

解析结果分为：

- `video`：可直接导入单条视频。
- `channel`：进入博主同步流程。
- `playlist`：作为后续能力，MVP 可提示暂不支持。
- `unknown`：返回清晰错误，不进入任务队列。

## Backend Design

新增模块建议：

- `voxpress/pipeline/youtube_url.py`
  - URL 解析、canonical URL 生成、video id / channel id / handle 识别。
- `voxpress/pipeline/youtube_oembed.py`
  - oEmbed 请求、基础视频信息提取。
- `voxpress/pipeline/youtube_rss.py`
  - RSS feed 拉取、Atom XML 解析、最近视频列表同步。
- `voxpress/pipeline/youtube_ytdlp.py`
  - `yt-dlp` 元数据、字幕、自动字幕、音频抽取封装。
- `voxpress/youtube_sync.py`
  - 频道 upsert、视频 upsert、自动任务创建。

现有 `TaskRunner._extractor_backend()` 需要改为按任务 URL 或 `Video.creator.platform` 选择 extractor：

- `douyin` -> `DouyinWebExtractor`
- `youtube` -> `YoutubeExtractor`
- `stub` -> `StubExtractor`

`YoutubeExtractor` 的处理顺序：

1. 读取缓存中的字幕或音频 artifact。
2. 尝试 `yt-dlp` 字幕。
3. 如果字幕存在，直接生成 `TranscriptResult`，跳过音频 ASR。
4. 如果没有字幕，且 YouTube 音频处理开关打开，则下载音频并走 ASR。
5. 如果字幕和音频都不可用，任务失败为 `transcribe_failed`，但视频和博主元数据保留。

## Frontend Design

- 首页输入框文案改为支持抖音和 YouTube 链接。
- 博主列表增加平台 badge：抖音 / YouTube。
- YouTube 博主详情页按钮显示“在 YouTube 查看”。
- 视频列表和文章详情页支持 YouTube iframe 播放。
- 对未知统计显示 `—`，不要显示 `0`。
- 对字幕/音频增强能力增加轻提示：
  - “优先使用公开视频字幕。”
  - “没有字幕时会尝试抽取音频转写。”

## Execution Plan

1. 新增 YouTube URL resolver 和单元测试。
2. 新增 oEmbed client，支持单条视频基础导入。
3. 新增 YouTube RSS client，支持已知 channel id 的最近视频同步。
4. 使用 `yt-dlp` 解析 `@handle` 到 channel id，结果缓存到 `creators.external_id`。
5. 博主同步流程支持 `platform="youtube"`。
6. 前端增加平台 badge、YouTube 外链和 iframe 播放。
7. 增强层接入 `yt-dlp` 字幕提取，优先生成 transcript。
8. 增加 YouTube 音频处理配置开关，再启用音频下载 + ASR。

## Verification

- URL resolver 覆盖 watch、youtu.be、shorts、embed、channel、handle、playlist。
- oEmbed client 对公开视频返回标题、作者、封面。
- RSS client 能解析最近视频并去重入库。
- YouTube 视频导入失败时不影响抖音链路。
- 没有字幕且音频处理关闭时，任务给出清晰错误。
- 前端未知统计不显示为真实 `0`。
- iframe 在桌面和移动端均可播放，布局不溢出。

## Risks

- RSS 只适合最近视频监控，不适合历史归档。
- oEmbed 信息有限，不能支撑完整 analytics。
- `yt-dlp` 依赖 YouTube 页面和播放接口行为，可能因平台调整失效。
- 字幕和音频能力涉及版权和平台服务条款边界；虽然本产品定位为个人工具，仍应保留配置开关和清晰失败提示。
- 批量同步需要限流和缓存，避免触发平台风控。

## Open Questions

- 产品是否接受 YouTube 基础层没有播放量、点赞、评论数？
- 是否需要为 YouTube 单独设计“字幕导入优先”的任务类型？
- `videos.id` 是否现在就做平台化迁移，还是先用 `youtube:{video_id}` 过渡？
- YouTube 音频处理开关放在配置文件，还是也暴露到设置页？
- 是否需要支持 playlist 作为独立博主/合集来源？

## References

- YouTube oEmbed endpoint: `https://www.youtube.com/oembed?url=...&format=json`
- YouTube channel RSS: `https://www.youtube.com/feeds/videos.xml?channel_id=UC...`
- yt-dlp: `https://github.com/yt-dlp/yt-dlp`
- YouTube Terms of Service: `https://www.youtube.com/t/terms`

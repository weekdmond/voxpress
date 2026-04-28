# cases/ — eval set

每个 `case_*.json` 是一条 eval 数据。整个 prompt 调优的**地基**就是这几个 case 的质量和代表性。

## 一个 case 包含什么

```json
{
  "case_id": "case_001",
  "creator": "金枪大叔",
  "title_hint": "（可选）",
  "duration_sec": 360,
  "transcript": "完整 ASR 文本…",
  "label": "中",
  "note": "结构散，标题像通稿，结尾烂尾"
}
```

最关键的两个字段：

- **transcript**：原始 ASR 文本（脏的就行，pipeline 自带预处理）
- **label + note**：你对**当前 voxpress 给这条 transcript 跑出的输出**的评价。一句话写"差在哪"，这句话就是 prompt 调优的方向盘。

## 怎么挑 case

8–10 个，覆盖：

- **不同长度**：短（< 1 分钟）、中（3–5 分钟）、长（> 8 分钟）各 2-3 个
- **不同主题**：干货科普、观点输出、闲聊、故事、采访 各来一两个
- **不同质量基线**：现有输出"优 / 中 / 差"各几个——只挑差的会让你看不到 prompt 改动是否在好 case 上反而退化

## label 是给"现有输出"打的，不是给 transcript 打的

容易混淆的一点：

| label 的对象 | ✅ 对 | ❌ 错 |
|---|---|---|
| 当前 voxpress 跑出的文章 | 标"差" 因为输出口语化 | 标"差" 因为视频本来无聊 |

## note 字段的写法

不要写抽象的"质量不行"。写**具体失败模式**。
LLM 看不到你的吐槽，但你在调 prompt 时这条 note 会救你的命。

✅ 好的 note：
- "标题用了'我们今天聊聊'这种通稿开头"
- "把转写口头禅原样保留了，'对吧''然后''那个'到处都是"
- "中间举的两个例子被合并成一段，丢失了对比逻辑"
- "结尾结的是空话'让我们一起期待'，原视频实际给了具体建议"
- "杜撰了一个原视频没说的数字（'据报道 90% 的人...'）"

❌ 没用的 note：
- "质量不好"
- "不像文章"
- "AI 味太重"

## 命名

- 文件名 = `case_001.json` ~ `case_010.json`，三位数字方便排序
- 以 `_` 开头的文件会被 runner 跳过（如 `_template.json` 是模板）

## 怎么从 voxpress 拉 transcript

最快的方式是直接从 voxpress-api 的数据库里 copy 出来：

```bash
# 在 voxpress-api 的 venv 里
psql -h 127.0.0.1 -U voxpress -d voxpress -c "
SELECT t.id, c.name as creator, t.title, sr.output->>'text' as transcript
FROM tasks t
JOIN creators c ON c.id = t.creator_id
JOIN task_stage_runs sr ON sr.task_id = t.id AND sr.stage = 'transcribe'
WHERE t.status = 'success'
ORDER BY t.created_at DESC
LIMIT 20;
"
```

然后挑 8–10 个，把 transcript 拷进 `case_xxx.json`。

> 注意：本项目**不直接连 voxpress 数据库**——拉数据是一次性手工动作，不要写成自动同步，避免误改产线。

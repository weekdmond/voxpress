#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DB_URL = "postgresql://auston@localhost/voxpress"
CREATOR_ID = 4
OUT_DIR = Path("exports/fupeng_reviewed_book")
PREVIOUS_REPORT = OUT_DIR / "audit_report.csv"


PARTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("第一部 宏观周期与政策框架", "宏观经济", ("宏观", "政策", "财政", "货币", "利率", "通胀", "通缩", "经济周期", "流动性", "汇率")),
    ("第二部 债务、杠杆与资产负债表", "债务周期", ("债务", "杠杆", "负债", "现金流", "存款", "贷款", "净息差", "资产负债表")),
    ("第三部 房地产、人口与城市", "房地产", ("房地产", "楼市", "房价", "土地", "人口", "城市", "香港", "日本")),
    ("第四部 资本市场与投资风险", "资本市场", ("股市", "股票", "估值", "资产配置", "投资", "风险", "波动", "黄金", "债券", "雪球")),
    ("第五部 产业变迁与商业逻辑", "产业经济", ("产业", "企业", "平台", "消费", "新能源", "汽车", "电池", "音乐", "零售", "AI", "技术", "潮玩", "二次元", "IP", "酒", "品牌")),
    ("第六部 全球秩序、地缘与能源", "全球秩序", ("地缘", "战争", "美国", "欧洲", "俄乌", "能源", "石油", "金属", "关税", "全球")),
    ("第七部 个体选择、职业与生活财务", "个人财务", ("个人", "职业", "中年", "退休", "孩子", "收入", "消费主义", "家庭", "工资", "医生", "滑雪", "读书", "教育", "生活")),
]

DOMAIN_TAGS = [
    "低利率",
    "债务出清",
    "债务置换",
    "资产配置",
    "现金流管理",
    "资产负债表",
    "房地产周期",
    "人口结构",
    "城市分化",
    "地方债",
    "财政政策",
    "货币政策",
    "居民收入",
    "消费主义",
    "平台经济",
    "新能源汽车",
    "能源安全",
    "地缘政治",
    "产业周期",
    "商业模式",
    "资本市场",
    "估值逻辑",
    "风险偏好",
    "流动性危机",
    "通胀通缩",
    "汇率",
    "黄金",
    "加密货币",
    "AI",
    "职业规划",
    "中年危机",
    "财富管理",
    "日本经济",
    "美国经济",
    "欧洲经济",
    "统一大市场",
    "大宗商品",
    "金融监管",
    "医疗改革",
    "教育规划",
]

STOP_WORDS = {
    "这个",
    "那个",
    "一个",
    "一种",
    "其实",
    "就是",
    "所以",
    "然后",
    "因为",
    "但是",
    "我们",
    "他们",
    "你们",
    "如果",
    "可能",
    "现在",
    "没有",
    "什么",
    "怎么",
    "时候",
    "东西",
    "问题",
    "来讲",
    "对吧",
    "是吧",
    "当然了",
    "但是呢",
    "然后呢",
    "所以说呢",
}

FILLER_PATTERNS = [
    (re.compile(r"[ \t\r\f\v]+"), ""),
    (re.compile(r"\n{3,}"), "\n\n"),
    (re.compile(r"([。！？；])(?:啊|呀|嘛|呢|吧|啦|哈|哦)+"), r"\1"),
    (re.compile(r"(?:嗯|呃|额|啊)[,，。 ]*"), ""),
    (re.compile(r"(?:对不对|是不是|你知道吧|明白吧|是吧)[,，。?？ ]*"), "。"),
    (re.compile(r"[,，]{2,}"), "，"),
    (re.compile(r"[。]{2,}"), "。"),
]

NOISE_TERMS = (
    "福袋",
    "抽奖",
    "小助理",
    "购物车",
    "马克杯",
    "签名版",
    "直播间",
    "点赞",
    "关注",
    "公众号",
    "同名的公众号",
    "关键词",
    "评论区",
    "上链接",
    "读秒的时钟",
    "恶意剪辑",
    "线下读书会",
    "闭门读书会",
    "视频号",
    "东北偏北",
    "粉丝群",
    "直播回放",
    "开奖",
    "兑奖",
    "读书会",
    "橱窗",
    "库存",
    "邀请函",
)

SUBSTANCE_TERMS = tuple(word for _, _, words in PARTS for word in words) + tuple(DOMAIN_TAGS)

POLISH_REPLACEMENTS = [
    (re.compile(r"对对对+"), ""),
    (re.compile(r"(?:对吧|是吧|对不对|是不是|你知道吧|明白吧)[？?。；，,、 ]*"), "。"),
    (re.compile(r"(?:嗯|呃|额|啊|哎呀|哎呦)[，,。 ]*"), ""),
    (re.compile(r"(?:那当然了|当然了|当然|那么|然后呢|然后|所以说呢|所以说|其实呢|其实|也就是说)[，, ]*"), ""),
    (re.compile(r"^(?:那|对|好的|好|行|是|不是)[，,。 ]*"), ""),
    (re.compile(r"(?:呢|嘛|呀)(?=[，,。；？！])"), ""),
    (re.compile(r"呢"), ""),
    (re.compile(r"(?:简单讲|简单来讲)"), "简单说"),
    (re.compile(r"(?:用我的话说呢|用我的话说)"), "我认为"),
    (re.compile(r"(?:我们说|你会发现|大家要知道|大家肯定知道)[，, ]*"), ""),
    (re.compile(r"(?:这个|那个){2,}"), ""),
    (re.compile(r"(?<![一-龥])(?:这个|那个)(?=[一-龥])"), ""),
    (re.compile(r"([我你他她它咱])\1+"), r"\1"),
    (re.compile(r"([\u4e00-\u9fff]{1,2})\1{2,}"), r"\1"),
    (re.compile(r"([。！？；])(?:呢|啊|呀|嘛|吧|啦|哈|哦)+"), r"\1"),
    (re.compile(r"[，,]{2,}"), "，"),
    (re.compile(r"[。]{2,}"), "。"),
    (re.compile(r"^[，,。；、\s]+"), ""),
]


@dataclass
class Article:
    id: str
    video_id: str
    title: str
    source: str
    content_md: str
    tags: list[str]
    published_at: str
    duration_sec: int
    likes: int
    source_url: str


def run_psql_json(sql: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        ["psql", DB_URL, "-X", "-At", "-c", sql],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    payload = proc.stdout.strip()
    if not payload:
        return []
    data = json.loads(payload)
    return data or []


def fetch_articles() -> list[Article]:
    sql = f"""
select coalesce(json_agg(row_to_json(q)), '[]'::json)
from (
  select
    a.id::text,
    a.video_id,
    a.title,
    coalesce(t.corrected_text, t.raw_text, '') as source,
    a.content_md,
    coalesce(a.tags, '{{}}') as tags,
    to_char(v.published_at, 'YYYY-MM-DD') as published_at,
    v.duration_sec,
    v.likes,
    v.source_url
  from articles a
  join videos v on v.id = a.video_id
  left join transcripts t on t.video_id = a.video_id
  where a.creator_id = {CREATOR_ID}
  order by v.published_at desc, a.created_at desc
) q;
"""
    return [
        Article(
            id=row["id"],
            video_id=row["video_id"],
            title=row["title"],
            source=row["source"] or "",
            content_md=row["content_md"] or "",
            tags=list(row.get("tags") or []),
            published_at=row["published_at"] or "",
            duration_sec=int(row.get("duration_sec") or 0),
            likes=int(row.get("likes") or 0),
            source_url=row.get("source_url") or "",
        )
        for row in run_psql_json(sql)
    ]


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", "").replace("\xa0", "")
    for pattern, repl in FILLER_PATTERNS:
        text = pattern.sub(repl, text)
    text = re.sub(r"([。！？；])(?=[^\n])", r"\1\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def plain_md(md: str) -> str:
    md = re.split(r"\n## 背景注\b", md, maxsplit=1)[0]
    md = re.sub(r"```.*?```", "", md, flags=re.S)
    md = re.sub(r"`([^`]+)`", r"\1", md)
    md = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", md)
    md = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)
    md = re.sub(r"^[>#*\-\s]+", "", md, flags=re.M)
    md = re.sub(r"#+\s*", "", md)
    return re.sub(r"\s+", "", md)


def han_len(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def grams(text: str, n: int = 3) -> set[str]:
    compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", text)
    if len(compact) <= n:
        return {compact} if compact else set()
    return {compact[i : i + n] for i in range(len(compact) - n + 1)}


def keyword_counter(text: str) -> Counter[str]:
    words = re.findall(r"[\u4e00-\u9fff]{2,6}|[A-Za-z][A-Za-z0-9+.-]{1,}", text)
    out: Counter[str] = Counter()
    for word in words:
        if word in STOP_WORDS:
            continue
        if len(word) == 2 and word in {"可以", "不是", "还是", "已经", "一定", "很多", "这种"}:
            continue
        out[word] += 1
    return out


def score_article(article: Article, content_md: str | None = None) -> dict[str, float]:
    source = plain_md(article.source)
    body = plain_md(content_md if content_md is not None else article.content_md)
    source_len = max(1, han_len(source))
    body_len = han_len(body)
    length_ratio = body_len / source_len
    source_grams = grams(source, 3)
    body_grams = grams(body, 3)
    gram_recall = len(source_grams & body_grams) / max(1, len(source_grams))
    src_keywords = {k for k, v in keyword_counter(source).most_common(80) if v >= 2 or len(k) >= 4}
    body_keywords = set(keyword_counter(body))
    keyword_recall = len(src_keywords & body_keywords) / max(1, len(src_keywords))
    return {
        "source_len": float(source_len),
        "body_len": float(body_len),
        "length_ratio": length_ratio,
        "gram_recall": gram_recall,
        "keyword_recall": keyword_recall,
    }


def split_sentences(text: str, title: str = "", *, drop_noise: bool = True) -> list[str]:
    normalized = normalize_text(text)
    parts: list[str] = []
    for line in normalized.splitlines():
        line = line.strip()
        if not line:
            continue
        chunks = re.split(r"(?<=[。！？；])", line)
        for chunk in chunks:
            chunk = chunk.strip(" ，,")
            if not chunk:
                continue
            chunk = polish_sentence(chunk)
            if not chunk:
                continue
            if drop_noise and should_drop_sentence(chunk, title=title):
                continue
            if not re.search(r"[。！？；]$", chunk):
                chunk += "。"
            parts.append(chunk)
    return parts


def polish_sentence(sentence: str) -> str:
    sentence = sentence.strip()
    for pattern, repl in POLISH_REPLACEMENTS:
        sentence = pattern.sub(repl, sentence)
    sentence = re.sub(r"([。！？；])(?=[一-龥A-Za-z0-9])", r"\1", sentence)
    sentence = re.sub(r"([，,])([。！？；])", r"\2", sentence)
    sentence = re.sub(r"[，,]$", "。", sentence)
    sentence = re.sub(r"。{2,}", "。", sentence)
    return sentence.strip(" ，,、")


def should_drop_sentence(sentence: str, *, title: str = "") -> bool:
    if any(term in sentence for term in NOISE_TERMS) and not any(term in title for term in NOISE_TERMS):
        return True
    if re.search(r"(点击|关注|联系|购买|拍下|库存|席位|回放|主页|头像|评论区|朋友圈|上链接)", sentence) and not any(
        term in title for term in ("推荐", "澄清", "春节", "祝福")
    ):
        return True
    if re.search(r"(签在|展示一下|打包|晾干|中奖|先到先得|没有邀请函|东北证券主办|挂在橱窗)", sentence):
        return True
    if re.search(r"(直播标题|带大家一起|读一读书|推荐大家.*书|快八十|没什么顾虑|真正意义上的真话)", sentence):
        return True
    if re.search(r"(有朋友问|我们来看一下评论|来念几条评论|刚刚有朋友|评论有朋友)", sentence):
        return True
    if han_len(sentence) < 8 and not any(term in sentence for term in SUBSTANCE_TERMS):
        return True
    return False


def pick_part(title: str, source: str, tags: list[str]) -> tuple[str, str]:
    haystack = f"{title} {' '.join(tags)} {source[:2000]}"
    best = PARTS[-1]
    best_score = -1
    for part, default_tag, kws in PARTS:
        score = sum(haystack.count(kw) * (2 if kw in title or kw in tags else 1) for kw in kws)
        if score > best_score:
            best = (part, default_tag, kws)
            best_score = score
    if best_score <= 0:
        return PARTS[-1][0], PARTS[-1][1]
    return best[0], best[1]


def derive_tags(article: Article, part_tag: str) -> list[str]:
    text = f"{article.title}\n{' '.join(article.tags)}\n{article.source}"
    tags: list[str] = [part_tag]
    for tag in article.tags:
        tag = tag.strip()
        if is_good_tag(tag) and tag not in tags:
            tags.append(tag)
    for word in DOMAIN_TAGS:
        if len(tags) >= 6:
            break
        if word in text and word not in tags:
            tags.append(word)
    return tags[:6]


def is_good_tag(tag: str) -> bool:
    if not tag or tag in {"付鹏", "付鹏财经"}:
        return False
    if tag in STOP_WORDS:
        return False
    if any(filler in tag for filler in ("对吧", "呢", "啊", "嘛", "当然了", "然后")):
        return False
    if len(tag) > 12:
        return False
    if tag.endswith(("的", "了", "呢")):
        return False
    return True


def controlled_keywords(chunk: str) -> list[str]:
    found: list[str] = []
    for word in DOMAIN_TAGS:
        if word in chunk:
            found.append(word)
    for _, _, kws in PARTS:
        for word in kws:
            if word in chunk and word not in found:
                found.append(word)
    return found


def heading_for(chunk: str, fallback: str) -> str:
    words = controlled_keywords(chunk)
    for word in words:
        if len(word) >= 2 and word not in STOP_WORDS:
            return f"围绕{word}的判断"
    return fallback


def heading_text(chunk: str, idx: int, used: Counter[str]) -> str:
    base = heading_for(chunk, f"第{idx}层论证")
    if idx == 1:
        base = base.replace("围绕", "先看")
    if used[base] == 0:
        used[base] += 1
        return base
    keyword = controlled_keywords(chunk)
    if keyword:
        candidate = f"{keyword[min(used[base], len(keyword) - 1)]}的进一步展开"
        used[base] += 1
        return candidate
    used[base] += 1
    return f"第{idx}层论证"


def regroup_sentences(sentences: list[str], target_chars: int) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    size = 0
    for sentence in sentences:
        current.append(sentence)
        size += han_len(sentence)
        if size >= target_chars and len(current) >= 4:
            groups.append(current)
            current = []
            size = 0
    if current:
        if groups and han_len("".join(current)) < target_chars * 0.35:
            groups[-1].extend(current)
        else:
            groups.append(current)
    return groups


def paragraphize(group: list[str]) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    size = 0
    for sentence in group:
        current.append(sentence)
        size += han_len(sentence)
        if len(current) >= 3 or size >= 180:
            paragraphs.append(polish_paragraph("".join(current)))
            current = []
            size = 0
    if current:
        paragraphs.append(polish_paragraph("".join(current)))
    return paragraphs


def polish_paragraph(paragraph: str) -> str:
    paragraph = re.sub(r"。(?=[”」』])", "", paragraph)
    paragraph = re.sub(r"([。！？；])(?=[一-龥A-Za-z0-9])", r"\1", paragraph)
    paragraph = re.sub(r"([。！？；]){2,}", r"\1", paragraph)
    paragraph = re.sub(r"([，,])([。！？；])", r"\2", paragraph)
    return paragraph.strip()


def rebuild_article(article: Article, tags: list[str]) -> str:
    sentences = split_sentences(article.source, title=article.title)
    if not sentences:
        return article.content_md.strip()
    source_len = han_len(plain_md(article.source))
    target = 850 if source_len < 4500 else 1250
    groups = regroup_sentences(sentences, target)
    lines: list[str] = []
    used_headings: Counter[str] = Counter()
    for idx, group in enumerate(groups, start=1):
        chunk = "".join(group)
        heading = heading_text(chunk, idx, used_headings)
        lines.extend([f"## {heading}", ""])
        for paragraph in paragraphize(group):
            lines.extend([paragraph, ""])
    if tags:
        lines.extend(["## 归类标签", "", "、".join(f"`{tag}`" for tag in tags), ""])
    md = "\n".join(lines).strip()
    if score_article(article, md)["length_ratio"] < 0.85:
        md = append_supplement(article, md)
    return md


def append_supplement(article: Article, md: str) -> str:
    used = set(split_sentences(md, title=article.title, drop_noise=False))
    all_sentences = split_sentences(article.source, title=article.title, drop_noise=False)
    supplement: list[str] = []
    for sentence in all_sentences:
        if sentence in used:
            continue
        if should_drop_sentence(sentence, title=article.title):
            continue
        supplement.append(sentence)
        candidate = f"{md}\n\n## 补充论证与案例\n\n" + "\n\n".join(
            paragraphize(part)[0] if len(part) == 1 else "\n\n".join(paragraphize(part))
            for part in regroup_sentences(supplement, 520)
        )
        if score_article(article, candidate)["length_ratio"] >= 0.85:
            return candidate.strip()
    if supplement:
        body = "\n\n".join(
            "\n\n".join(paragraphize(part)) for part in regroup_sentences(supplement, 520)
        )
        return f"{md}\n\n## 补充论证与案例\n\n{body}".strip()
    return md


def load_forced_rebuild_ids() -> set[str]:
    if not PREVIOUS_REPORT.exists():
        return set()
    ids: set[str] = set()
    with PREVIOUS_REPORT.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "rebuilt":
                ids.add(str(row.get("id") or ""))
    return ids


def safe_slug(text: str, max_len: int = 64) -> str:
    text = re.sub(r"[\\/:*?\"<>|#`]+", "", text).strip()
    text = re.sub(r"\s+", "-", text)
    return text[:max_len] or "untitled"


def write_article_file(index: int, article: Article, part: str, tags: list[str], md: str, status: str) -> Path:
    filename = f"{index:03d}-{safe_slug(article.title)}.md"
    path = OUT_DIR / "articles" / filename
    frontmatter = {
        "id": article.id,
        "video_id": article.video_id,
        "title": article.title,
        "published_at": article.published_at,
        "part": part,
        "tags": tags,
        "review_status": status,
        "source_url": article.source_url,
    }
    yaml = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            yaml.append(f"{key}: [{', '.join(json.dumps(v, ensure_ascii=False) for v in value)}]")
        else:
            yaml.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    yaml.extend(["---", "", f"# {article.title}", "", md.strip(), ""])
    path.write_text("\n".join(yaml), encoding="utf-8")
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "articles").mkdir(exist_ok=True)
    articles = fetch_articles()
    forced_rebuild_ids = load_forced_rebuild_ids()
    rows: list[dict[str, Any]] = []
    by_part: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tag_counter: Counter[str] = Counter()
    rebuilt_count = 0

    for idx, article in enumerate(articles, start=1):
        part, part_tag = pick_part(article.title, article.source, article.tags)
        tags = derive_tags(article, part_tag)
        before = score_article(article)
        needs_rebuild = before["length_ratio"] < 0.85 or article.id in forced_rebuild_ids
        status = "rebuilt" if needs_rebuild else "passed"
        final_md = rebuild_article(article, tags) if needs_rebuild else article.content_md.strip()
        after = score_article(article, final_md)
        if needs_rebuild:
            rebuilt_count += 1
        file_path = write_article_file(idx, article, part, tags, final_md, status)
        for tag in tags:
            tag_counter[tag] += 1
        row = {
            "index": idx,
            "id": article.id,
            "title": article.title,
            "published_at": article.published_at,
            "part": part,
            "tags": " / ".join(tags),
            "status": status,
            "source_len": int(before["source_len"]),
            "old_len": int(before["body_len"]),
            "old_ratio": round(before["length_ratio"], 3),
            "old_keyword_recall": round(before["keyword_recall"], 3),
            "new_len": int(after["body_len"]),
            "new_ratio": round(after["length_ratio"], 3),
            "new_keyword_recall": round(after["keyword_recall"], 3),
            "file": str(file_path),
            "source_url": article.source_url,
        }
        rows.append(row)
        by_part[part].append(row)

    report_csv = OUT_DIR / "audit_report.csv"
    with report_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary_lines = [
        "# 付鹏的财经世界：审稿与归档报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 审核文章：{len(rows)} 篇",
        f"- 重新整理润色：{rebuilt_count} 篇",
        f"- 原稿比例低于 85% 的旧稿：{sum(1 for r in rows if r['old_ratio'] < 0.85)} 篇",
        f"- 修订后低于 85% 的稿件：{sum(1 for r in rows if r['new_ratio'] < 0.85)} 篇",
        "",
        "## 全局标签",
        "",
        ", ".join(f"`{tag}`({count})" for tag, count in tag_counter.most_common(40)),
        "",
        "## 书籍式目录",
        "",
    ]
    for part, _, _ in PARTS:
        items = by_part.get(part, [])
        if not items:
            continue
        summary_lines.extend([f"### {part}", ""])
        for row in items:
            summary_lines.append(
                f"- [{row['title']}](articles/{Path(row['file']).name}) "
                f"（{row['published_at']}，{row['status']}，tags: {row['tags']}）"
            )
        summary_lines.append("")
    (OUT_DIR / "README.md").write_text("\n".join(summary_lines), encoding="utf-8")

    book_lines = [
        "# 付鹏的财经世界：财经观察整理稿",
        "",
        "> 本书稿按全局主题重新归类；标记为 rebuilt 的章节已按原稿重新整理润色，优先保证内容比例与原意保真。",
        "",
    ]
    for part, _, _ in PARTS:
        items = by_part.get(part, [])
        if not items:
            continue
        book_lines.extend([f"# {part}", ""])
        for row in items:
            article_path = Path(row["file"])
            text = article_path.read_text(encoding="utf-8")
            body = text.split("---", 2)[-1].strip()
            book_lines.extend([body, "\n---\n"])
    (OUT_DIR / "付鹏的财经世界-审稿归类书稿.md").write_text("\n".join(book_lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "articles": len(rows),
                "rebuilt": rebuilt_count,
                "old_below_85": sum(1 for r in rows if r["old_ratio"] < 0.85),
                "new_below_85": sum(1 for r in rows if r["new_ratio"] < 0.85),
                "out_dir": str(OUT_DIR),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

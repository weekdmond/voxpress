from __future__ import annotations

import re
from typing import Any, Mapping

ENTITY_KEYS = ("creators", "people", "organizations", "brands", "products", "places", "events")

DEFAULT_TOPIC_TAXONOMY: list[dict[str, Any]] = [
    {
        "topic": "金融投资",
        "subtopics": ["宏观经济", "股票市场", "资产配置", "房产楼市", "债务周期"],
    },
    {
        "topic": "商业经营",
        "subtopics": ["品牌营销", "商业模式", "渠道销售", "组织管理", "创业复盘"],
    },
    {
        "topic": "科技数码",
        "subtopics": ["AI大模型", "半导体", "硬件产品", "软件工具", "技术趋势"],
    },
    {
        "topic": "内容创作",
        "subtopics": ["个人品牌", "内容运营", "流量增长", "IP打造", "表达方法"],
    },
    {
        "topic": "社会观察",
        "subtopics": ["教育", "婚育家庭", "职场", "消费心理", "地缘政治"],
    },
    {
        "topic": "个人成长",
        "subtopics": ["认知方法", "职业发展", "情绪管理", "学习方法", "人际关系"],
    },
]

DEFAULT_TOPIC_SYNONYMS: dict[str, str] = {
    "AI": "科技数码/AI大模型",
    "大模型": "科技数码/AI大模型",
    "个人IP": "内容创作/个人品牌",
    "个人IP打造": "内容创作/IP打造",
    "品牌营销": "商业经营/品牌营销",
    "商业思维": "商业经营/商业模式",
    "商业逻辑": "商业经营/商业模式",
    "宏观经济": "金融投资/宏观经济",
    "资本市场": "金融投资/股票市场",
    "房地产": "金融投资/房产楼市",
    "地缘政治": "社会观察/地缘政治",
    "内容创作": "内容创作/内容运营",
}

GENERIC_TAGS = {
    "思考",
    "分享",
    "干货",
    "认知",
    "观点",
    "知识",
    "经验",
    "解读",
    "分析",
    "方法",
    "建议",
    "观察",
}


def normalize_taxonomy_nodes(value: Any) -> list[dict[str, Any]]:
    nodes = value if isinstance(value, list) else DEFAULT_TOPIC_TAXONOMY
    normalized: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        topic = _clean_label(node.get("topic"), max_len=24)
        if not topic:
            continue
        raw_subtopics = node.get("subtopics") or []
        if not isinstance(raw_subtopics, list):
            raw_subtopics = []
        subtopics = _dedupe(
            _clean_label(subtopic, max_len=24)
            for subtopic in raw_subtopics
            if _clean_label(subtopic, max_len=24)
        )
        normalized.append({"topic": topic, "subtopics": subtopics})
    return normalized or DEFAULT_TOPIC_TAXONOMY


def topic_paths(taxonomy: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for node in taxonomy:
        topic = _clean_label(node.get("topic"), max_len=24)
        if not topic:
            continue
        subtopics = node.get("subtopics") or []
        if not subtopics:
            paths.append(topic)
            continue
        for subtopic in subtopics:
            clean_subtopic = _clean_label(subtopic, max_len=24)
            if clean_subtopic:
                paths.append(f"{topic}/{clean_subtopic}")
    return _dedupe(paths)


def normalize_synonyms(value: Any, *, allowed_paths: list[str]) -> dict[str, str]:
    raw = value if isinstance(value, Mapping) else DEFAULT_TOPIC_SYNONYMS
    allowed = set(allowed_paths)
    synonyms: dict[str, str] = {}
    for key, target in raw.items():
        clean_key = _clean_label(key, max_len=24)
        clean_target = _clean_topic_path(target)
        if clean_key and clean_target in allowed:
            synonyms[clean_key] = clean_target
    return synonyms


def normalize_topic_selection(
    values: Any,
    *,
    allowed_paths: list[str],
    synonyms: Mapping[str, str] | None = None,
    max_items: int = 3,
) -> list[str]:
    raw_items = values if isinstance(values, list) else []
    allowed = set(allowed_paths)
    by_subtopic = _unique_subtopic_map(allowed_paths)
    normalized: list[str] = []
    for item in raw_items:
        value = _clean_topic_path(item)
        if not value:
            continue
        mapped = value if value in allowed else None
        if mapped is None and value in (synonyms or {}):
            mapped = str((synonyms or {})[value])
        if mapped is None and "/" not in value:
            mapped = by_subtopic.get(value)
        if mapped and mapped in allowed:
            normalized.append(mapped)
    return _dedupe(normalized)[:max_items]


def clean_keyword_tags(values: Any, *, max_items: int = 4, max_len: int = 16) -> list[str]:
    raw_items = values if isinstance(values, list) else []
    cleaned: list[str] = []
    for item in raw_items:
        tag = _clean_label(item, max_len=max_len)
        if not tag or tag in GENERIC_TAGS:
            continue
        if "/" in tag:
            continue
        cleaned.append(tag)
    return _dedupe(cleaned)[:max_items]


def normalize_article_entities(
    value: Any,
    *,
    creator_hint: str = "",
    max_items_per_key: int = 8,
) -> dict[str, list[str]]:
    raw = value if isinstance(value, Mapping) else {}
    entities: dict[str, list[str]] = {}
    for key in ENTITY_KEYS:
        values = raw.get(key)
        if not isinstance(values, list):
            values = []
        cleaned = [_clean_label(item, max_len=24) for item in values]
        entities[key] = _dedupe(item for item in cleaned if item)[:max_items_per_key]

    creator = _clean_label(creator_hint, max_len=24)
    if creator:
        entities["creators"] = _dedupe([creator, *entities["creators"]])[:max_items_per_key]
    return entities


def clean_article_keywords(
    values: Any,
    *,
    entities: Mapping[str, list[str]] | None = None,
    creator_hint: str = "",
    max_items: int = 4,
) -> list[str]:
    blocked = _entity_blocklist(entities or {}, creator_hint=creator_hint)
    tags: list[str] = []
    for tag in clean_keyword_tags(values, max_items=24):
        if _is_blocked_tag(tag, blocked):
            continue
        tags.append(tag)
    return _dedupe(tags)[:max_items]


def _clean_topic_path(value: Any) -> str:
    text = str(value or "").replace("／", "/").strip().strip("#")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"/+", "/", text).strip("/")
    return text[:64]


def _clean_label(value: Any, *, max_len: int) -> str:
    text = str(value or "").strip().strip("#")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，,;；]+$", "", text)
    return text[:max_len]


def _dedupe(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _entity_blocklist(entities: Mapping[str, list[str]], *, creator_hint: str) -> set[str]:
    blocked = {_clean_label(creator_hint, max_len=24)}
    for values in entities.values():
        if not isinstance(values, list):
            continue
        for value in values:
            clean = _clean_label(value, max_len=24)
            if clean:
                blocked.add(clean)
    return {item for item in blocked if item}


def _is_blocked_tag(tag: str, blocked: set[str]) -> bool:
    if tag in blocked:
        return True
    return any(len(item) >= 2 and (tag in item or item in tag) for item in blocked)


def _unique_subtopic_map(paths: list[str]) -> dict[str, str]:
    buckets: dict[str, list[str]] = {}
    for path in paths:
        subtopic = path.rsplit("/", 1)[-1]
        buckets.setdefault(subtopic, []).append(path)
    return {subtopic: values[0] for subtopic, values in buckets.items() if len(values) == 1}

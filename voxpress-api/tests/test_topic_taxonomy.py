from __future__ import annotations

from voxpress.topic_taxonomy import (
    clean_article_keywords,
    clean_keyword_tags,
    normalize_article_entities,
    normalize_topic_selection,
)


def test_normalize_topic_selection_accepts_paths_synonyms_and_unique_subtopics() -> None:
    allowed = ["金融投资/股票市场", "科技数码/AI大模型", "商业经营/品牌营销"]

    assert normalize_topic_selection(
        ["股票市场", "AI", "不存在"],
        allowed_paths=allowed,
        synonyms={"AI": "科技数码/AI大模型"},
    ) == ["金融投资/股票市场", "科技数码/AI大模型"]


def test_clean_keyword_tags_removes_generic_noise_and_paths() -> None:
    assert clean_keyword_tags(["#茅台", " 思考 ", "金融投资/股票市场", "渠道 库存", "茅台"]) == [
        "茅台",
        "渠道库存",
    ]


def test_entities_are_normalized_and_removed_from_article_keywords() -> None:
    entities = normalize_article_entities(
        {
            "people": [" 雷军 ", "雷军"],
            "brands": ["小米"],
            "places": ["北京"],
            "unknown": ["ignored"],
        },
        creator_hint="金枪大叔",
    )

    assert entities["creators"] == ["金枪大叔"]
    assert entities["people"] == ["雷军"]
    assert entities["brands"] == ["小米"]
    assert clean_article_keywords(
        ["雷军", "小米汽车", "价格倒挂", "金枪大叔", "渠道库存"],
        entities=entities,
        creator_hint="金枪大叔",
    ) == ["价格倒挂", "渠道库存"]

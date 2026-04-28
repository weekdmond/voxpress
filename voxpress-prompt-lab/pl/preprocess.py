"""ASR 文本预处理：清洗口头禅、合并重复字、规范标点。

设计原则：宁可保留也不要过度清洗。这里只处理高置信度的 noise，
避免把博主特色（短句、停顿、重复强调）当 noise 删掉。
"""

from __future__ import annotations

import re


# 高置信度的纯口头禅 / filler，可以放心删
_FILLER_PATTERNS = [
    r"那个那个",
    r"嗯嗯",
    r"啊啊",
    r"呃呃",
    r"然后然后",
]

# 边界 filler——前后是标点或字符时才删
_BOUNDARY_FILLERS = [
    "嗯",
    "啊",
    "呃",
    "嗯哼",
]

# 重复 3+ 次的相邻同字（"哈哈哈哈" → "哈哈"）
_REPEAT_3 = re.compile(r"(.)\1{2,}")

# 多空白 / 多换行
_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def clean_transcript(text: str, *, aggressive: bool = False) -> str:
    """清洗 ASR 文本。

    aggressive=False（默认）：仅删除高置信度 noise。
    aggressive=True：额外删孤立的"嗯/啊/呃"等单字 filler。仅在 prompt 已显式要求保留风格时使用。
    """
    if not text:
        return text

    s = text

    # 重复 filler
    for p in _FILLER_PATTERNS:
        s = re.sub(p, "", s)

    # 重复字 → 收敛到 2 个
    s = _REPEAT_3.sub(r"\1\1", s)

    # 仅 aggressive 模式删孤立单字 filler
    if aggressive:
        for f in _BOUNDARY_FILLERS:
            # 前后是标点或行首/行尾时删
            s = re.sub(rf"(?:^|(?<=[，。？！；：\s\n])){re.escape(f)}(?=[，。？！；：\s\n]|$)", "", s)

    # 空白收敛
    s = _MULTI_SPACE.sub(" ", s)
    s = _MULTI_NEWLINE.sub("\n\n", s)
    s = s.strip()

    return s


def estimate_tokens(text: str) -> int:
    """粗估 token 数（中文按 1 char ≈ 1 token，英文按 4 chars ≈ 1 token）。

    仅供日志/预算用，不要用作真实账单。
    """
    if not text:
        return 0
    cn = sum(1 for c in text if "一" <= c <= "鿿")
    other = len(text) - cn
    return cn + max(1, other // 4)

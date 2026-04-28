#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import csv
import re
from pathlib import Path

import asyncpg

from voxpress.markdown import md_to_html, word_count_cn


DB_URL = "postgresql://auston@localhost/voxpress"
REPORT = Path("exports/fupeng_reviewed_book/audit_report.csv")


def read_body(path: Path, title: str) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2].strip()
    text = re.sub(rf"^#\s+{re.escape(title)}\s*", "", text).strip()
    text = re.split(r"\n## 归类标签\s*\n", text, maxsplit=1)[0].strip()
    return text


def load_rebuilt_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with REPORT.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] != "rebuilt":
                continue
            body = read_body(Path(row["file"]), row["title"])
            tags = [tag.strip() for tag in row["tags"].split(" / ") if tag.strip()]
            rows.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "content_md": body,
                    "content_html": md_to_html(body),
                    "word_count": word_count_cn(body),
                    "tags": tags,
                }
            )
    return rows


async def main() -> None:
    rows = load_rebuilt_rows()
    conn = await asyncpg.connect(DB_URL)
    try:
        async with conn.transaction():
            for row in rows:
                result = await conn.execute(
                    """
                    update articles
                       set content_md = $2,
                           content_html = $3,
                           word_count = $4,
                           tags = $5::text[],
                           updated_at = now()
                     where id = $1::uuid
                    """,
                    row["id"],
                    row["content_md"],
                    row["content_html"],
                    row["word_count"],
                    row["tags"],
                )
                if result != "UPDATE 1":
                    raise RuntimeError(f"Article update failed for {row['id']}: {result}")
    finally:
        await conn.close()
    print(f"updated {len(rows)} rebuilt articles")


if __name__ == "__main__":
    asyncio.run(main())

import uuid

import pytest
from pydantic import ValidationError

from voxpress.schemas import ArticleShareIn


def test_article_share_accepts_large_creator_batches() -> None:
    ids = [uuid.uuid4() for _ in range(422)]

    payload = ArticleShareIn(article_ids=ids)

    assert len(payload.article_ids) == 422


def test_article_share_keeps_a_high_sanity_limit() -> None:
    ids = [uuid.uuid4() for _ in range(1001)]

    with pytest.raises(ValidationError):
        ArticleShareIn(article_ids=ids)

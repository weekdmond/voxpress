"""add article topics

Revision ID: a7c9d2e4f6b1
Revises: e2a9b7c4d1f0
Create Date: 2026-04-28 16:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7c9d2e4f6b1"
down_revision: Union[str, Sequence[str], None] = "e2a9b7c4d1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column(
            "topics",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.create_index(
        "idx_articles_topics_gin",
        "articles",
        ["topics"],
        unique=False,
        postgresql_using="gin",
    )
    op.alter_column("articles", "topics", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_articles_topics_gin", table_name="articles")
    op.drop_column("articles", "topics")

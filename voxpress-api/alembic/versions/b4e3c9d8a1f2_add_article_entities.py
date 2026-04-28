"""add article entities

Revision ID: b4e3c9d8a1f2
Revises: a7c9d2e4f6b1
Create Date: 2026-04-28 17:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b4e3c9d8a1f2"
down_revision: Union[str, Sequence[str], None] = "a7c9d2e4f6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column(
            "entities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "idx_articles_entities_gin",
        "articles",
        ["entities"],
        unique=False,
        postgresql_using="gin",
    )
    op.alter_column("articles", "entities", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_articles_entities_gin", table_name="articles")
    op.drop_column("articles", "entities")

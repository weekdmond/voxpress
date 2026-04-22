"""add updated_at to videos

Revision ID: e6a9d96e6c27
Revises: 7f3bdcda9c11
Create Date: 2026-04-21 10:08:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6a9d96e6c27"
down_revision: Union[str, Sequence[str], None] = "7f3bdcda9c11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    op.execute("UPDATE videos SET updated_at = COALESCE(discovered_at, NOW())")
    op.alter_column("videos", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("videos", "updated_at")

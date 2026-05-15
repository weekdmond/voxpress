"""add creator processing stop fields

Revision ID: d9f0a7c2b1e4
Revises: b4e3c9d8a1f2
Create Date: 2026-05-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9f0a7c2b1e4"
down_revision: Union[str, Sequence[str], None] = "b4e3c9d8a1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("creators", sa.Column("processing_stopped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("creators", sa.Column("processing_stop_reason", sa.Text(), nullable=True))
    op.create_index(
        "idx_creators_processing_stopped",
        "creators",
        ["processing_stopped_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_creators_processing_stopped", table_name="creators")
    op.drop_column("creators", "processing_stop_reason")
    op.drop_column("creators", "processing_stopped_at")

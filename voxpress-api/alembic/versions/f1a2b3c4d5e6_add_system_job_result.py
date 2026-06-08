"""add system job structured result

Revision ID: f1a2b3c4d5e6
Revises: d9f0a7c2b1e4
Create Date: 2026-06-08 12:35:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d9f0a7c2b1e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_job_runs",
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("system_job_runs", "result", server_default=None)


def downgrade() -> None:
    op.drop_column("system_job_runs", "result")

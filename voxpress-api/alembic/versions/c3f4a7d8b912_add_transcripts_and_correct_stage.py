"""add transcripts table and correct stage

Revision ID: c3f4a7d8b912
Revises: 9c1c9e4d6f21
Create Date: 2026-04-21 16:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3f4a7d8b912"
down_revision: Union[str, Sequence[str], None] = "9c1c9e4d6f21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column("articles", sa.Column("background_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "transcripts",
        sa.Column("video_id", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("corrections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correction_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("initial_prompt_used", sa.Text(), nullable=True),
        sa.Column("whisper_model", sa.Text(), nullable=True),
        sa.Column("whisper_language", sa.Text(), nullable=True),
        sa.Column("corrector_model", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "correction_status IN ('pending','ok','skipped','failed')",
            name="ck_transcripts_correction_status",
        ),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("video_id"),
    )
    op.create_index(
        "idx_transcripts_raw_trgm",
        "transcripts",
        ["raw_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"raw_text": "gin_trgm_ops"},
    )
    op.create_index(
        "idx_transcripts_corrected_trgm",
        "transcripts",
        ["corrected_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"corrected_text": "gin_trgm_ops"},
    )
    op.execute(
        """
        INSERT INTO transcripts (
            video_id,
            raw_text,
            segments,
            corrected_text,
            corrections,
            correction_status,
            created_at,
            updated_at
        )
        SELECT
            a.video_id,
            COALESCE(string_agg(ts.text, E'\n' ORDER BY ts.idx), ''),
            COALESCE(
                jsonb_agg(jsonb_build_array(ts.ts_sec, ts.text) ORDER BY ts.idx)
                    FILTER (WHERE ts.article_id IS NOT NULL),
                '[]'::jsonb
            ),
            COALESCE(string_agg(ts.text, E'\n' ORDER BY ts.idx), ''),
            '[]'::jsonb,
            'skipped',
            COALESCE(a.created_at, NOW()),
            COALESCE(a.updated_at, NOW())
        FROM articles a
        LEFT JOIN transcript_segments ts ON ts.article_id = a.id
        GROUP BY a.video_id, a.created_at, a.updated_at
        ON CONFLICT (video_id) DO NOTHING
        """
    )

    op.drop_constraint("ck_tasks_stage", "tasks", type_="check")
    op.create_check_constraint(
        "ck_tasks_stage",
        "tasks",
        "stage IN ('download','transcribe','correct','organize','save')",
    )

    op.alter_column("transcripts", "correction_status", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_tasks_stage", "tasks", type_="check")
    op.create_check_constraint(
        "ck_tasks_stage",
        "tasks",
        "stage IN ('download','transcribe','organize','save')",
    )
    op.drop_index("idx_transcripts_corrected_trgm", table_name="transcripts")
    op.drop_index("idx_transcripts_raw_trgm", table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_column("articles", "background_notes")

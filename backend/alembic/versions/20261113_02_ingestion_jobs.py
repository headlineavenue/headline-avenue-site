"""Add queued ingestion jobs and timestamped transcript segments.

Revision ID: 20261113_02
Revises: 20261112_01
Create Date: 2026-11-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261113_02"
down_revision = "20261112_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "source_transcript_segments" not in tables:
        op.create_table(
            "source_transcript_segments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "source_id",
                sa.String(36),
                sa.ForeignKey("sources.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("start_ms", sa.Integer(), nullable=False),
            sa.Column("end_ms", sa.Integer(), nullable=False),
            sa.Column("speaker", sa.String(80), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "source_id",
                "sequence",
                name="uq_source_transcript_segment_sequence",
            ),
        )
        op.create_index(
            "ix_source_transcript_segments_source_id",
            "source_transcript_segments",
            ["source_id"],
        )

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "ingestion_jobs" not in tables:
        op.create_table(
            "ingestion_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "workspace_id",
                sa.String(36),
                sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "source_id",
                sa.String(36),
                sa.ForeignKey("sources.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("job_type", sa.String(40), nullable=False),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_ingestion_jobs_workspace_id", "ingestion_jobs", ["workspace_id"])
        op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"])
        op.create_index("ix_ingestion_jobs_job_type", "ingestion_jobs", ["job_type"])
        op.create_index("ix_ingestion_jobs_provider", "ingestion_jobs", ["provider"])
        op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "ingestion_jobs" in tables:
        op.drop_table("ingestion_jobs")
    if "source_transcript_segments" in tables:
        op.drop_table("source_transcript_segments")

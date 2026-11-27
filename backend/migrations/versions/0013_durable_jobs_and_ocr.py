"""Add durable indexing jobs and OCR progress metadata."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("progress_stage", sa.String(length=20), nullable=False, server_default="uploading"))
    op.add_column("documents", sa.Column("ocr_used", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("documents", sa.Column("ocr_confidence", sa.Float(), nullable=True))
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_run_after", "jobs", ["run_after"])
    op.create_index("ix_jobs_status_run_after", "jobs", ["status", "run_after"])


def downgrade():
    op.drop_index("ix_jobs_status_run_after", table_name="jobs")
    op.drop_index("ix_jobs_run_after", table_name="jobs")
    op.drop_table("jobs")
    op.drop_column("documents", "ocr_confidence")
    op.drop_column("documents", "ocr_used")
    op.drop_column("documents", "progress_stage")

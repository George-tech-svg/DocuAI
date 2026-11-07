"""Align the legacy document status enum with the application model.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
from sqlalchemy import inspect, String
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    """Convert legacy PostgreSQL enum status columns to varchar safely."""
    inspector = inspect(op.get_bind())
    if "documents" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("documents")}
    status = columns.get("status")
    if status is None or not isinstance(status["type"], postgresql.ENUM):
        return

    # Remove a possibly enum-typed default before changing the column type.
    op.execute("ALTER TABLE documents ALTER COLUMN status DROP DEFAULT")
    op.alter_column(
        "documents",
        "status",
        existing_type=status["type"],
        type_=String(length=10),
        existing_nullable=status["nullable"],
        postgresql_using="status::text",
    )
    op.execute("ALTER TABLE documents ALTER COLUMN status SET DEFAULT 'pending'")


def downgrade():
    # Keep the text representation so this migration cannot discard statuses.
    pass

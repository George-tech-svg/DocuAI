"""Allow current conversation inserts on databases with the legacy flag.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
from sqlalchemy import inspect, text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    """Keep old archive data and default new legacy-column values to false."""
    inspector = inspect(op.get_bind())
    if "conversations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("conversations")}
    if "is_archived" in columns:
        op.alter_column(
            "conversations",
            "is_archived",
            server_default=text("false"),
        )


def downgrade():
    # Keep the default in place so rollback cannot reintroduce broken inserts.
    pass

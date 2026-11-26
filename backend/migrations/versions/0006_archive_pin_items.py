"""Add archive and pin state to folders, files, and chats."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    for table in ("knowledge_bases", "documents", "conversations"):
        if table not in inspector.get_table_names():
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in ("is_archived", "is_pinned"):
            if column not in existing:
                op.add_column(table, sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    pass

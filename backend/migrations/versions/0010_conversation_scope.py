"""Persist whether a chat is scoped to a document or a folder."""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversations",
        sa.Column("scope_type", sa.String(length=20), nullable=False, server_default="document"),
    )


def downgrade():
    op.drop_column("conversations", "scope_type")

"""Store rewritten standalone search queries on user chat messages."""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("messages", sa.Column("metadata_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("messages", "metadata_json")

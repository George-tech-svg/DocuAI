"""Allow accounts created through Google to have no password."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)


def downgrade():
    # Google-only accounts cannot be safely converted back to password accounts.
    pass

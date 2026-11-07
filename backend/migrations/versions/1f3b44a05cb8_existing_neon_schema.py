"""Bridge the existing Neon database revision to this migration history.

Revision ID: 1f3b44a05cb8
Revises:

Neon's alembic_version table already contains this revision, but the original
migration file was not included in the repository. This no-op bridge lets
Alembic continue forward without resetting or restamping the live database.
"""

revision = "1f3b44a05cb8"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    # Deliberately do not remove or alter schema or user data.
    pass

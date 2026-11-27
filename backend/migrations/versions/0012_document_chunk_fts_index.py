"""Index document passage text for built-in PostgreSQL keyword search."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX ix_document_chunks_content_fts "
        "ON document_chunks USING GIN (to_tsvector('simple', content))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_fts")

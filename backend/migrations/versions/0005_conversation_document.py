"""Attach saved chat conversations to their selected document.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "conversations" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("conversations")}
    if "document_id" not in columns:
        op.add_column(
            "conversations",
            sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if "documents" in tables:
        foreign_keys = inspector.get_foreign_keys("conversations")
        has_document_fk = any(
            key.get("constrained_columns") == ["document_id"]
            and key.get("referred_table") == "documents"
            for key in foreign_keys
        )
        if not has_document_fk:
            op.create_foreign_key(
                "fk_conversations_document_id_documents",
                "conversations",
                "documents",
                ["document_id"],
                ["id"],
                ondelete="SET NULL",
            )

    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("conversations")}
    if "ix_conversations_document_id" not in indexes:
        op.create_index("ix_conversations_document_id", "conversations", ["document_id"])


def downgrade():
    # Keep conversation-to-document links intact if a deployment is rolled back.
    pass

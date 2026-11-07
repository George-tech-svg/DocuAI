"""Align safe legacy column differences with the application models.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())

    if "messages" in inspector.get_table_names():
        columns = {column["name"]: column for column in inspector.get_columns("messages")}
        role = columns.get("role")
        if role and isinstance(role["type"], sa.String):
            current_length = role["type"].length
            if current_length is not None and current_length < 20:
                op.alter_column(
                    "messages",
                    "role",
                    existing_type=role["type"],
                    type_=sa.String(length=20),
                    existing_nullable=role["nullable"],
                )

    if "conversations" in inspector.get_table_names():
        columns = {column["name"]: column for column in inspector.get_columns("conversations")}
        knowledge_base_id = columns.get("knowledge_base_id")
        if knowledge_base_id and not knowledge_base_id["nullable"]:
            op.alter_column(
                "conversations",
                "knowledge_base_id",
                existing_type=knowledge_base_id["type"],
                nullable=True,
            )


def downgrade():
    # Widening a column and allowing NULL are intentionally irreversible here:
    # tightening them could truncate or reject user data created after upgrade.
    pass

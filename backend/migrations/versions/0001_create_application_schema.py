"""Create DocuMind tables and add compatible missing columns.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

from app.db.base import Base
from app import models  # noqa: F401 - register all model metadata

revision = "0001"
down_revision = "1f3b44a05cb8"
branch_labels = None
depends_on = None


def _default_for_existing_rows(column):
    """Return a temporary SQL default where the model has a safe Python default."""
    if column.name in {"created_at", "updated_at"}:
        return sa.text("CURRENT_TIMESTAMP")
    default = column.default
    if default is None or not default.is_scalar:
        return None
    value = default.arg
    if isinstance(value, bool):
        return sa.text("TRUE" if value else "FALSE")
    if isinstance(value, (int, float)):
        return sa.text(str(value))
    if isinstance(value, str):
        return sa.text("'" + value.replace("'", "''") + "'")
    return None


def _add_missing_columns(connection):
    inspector = inspect(connection)
    dialect = connection.dialect.identifier_preparer
    for table in Base.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue

        existing = {column["name"] for column in inspector.get_columns(table.name)}
        if all(column.name in existing for column in table.columns):
            continue

        table_name = dialect.quote(table.name)
        has_rows = connection.execute(
            text(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")
        ).scalar_one()

        for column in table.columns:
            if column.name in existing:
                continue
            if column.primary_key:
                raise RuntimeError(
                    f"Cannot safely add missing primary key {table.name}.{column.name}; "
                    "inspect and repair this Neon table manually before migrating."
                )

            default = _default_for_existing_rows(column)
            if has_rows and not column.nullable and default is None:
                raise RuntimeError(
                    f"Cannot safely add required column {table.name}.{column.name} "
                    "to a populated table because existing rows need real values. "
                    "Backfill those values first, then run npm run migrate again."
                )

            temporary_default = has_rows and not column.nullable and default is not None
            op.add_column(
                table.name,
                sa.Column(
                    column.name,
                    column.type,
                    nullable=column.nullable,
                    server_default=default if temporary_default else None,
                ),
            )
            if temporary_default:
                op.alter_column(table.name, column.name, server_default=None)

            existing.add(column.name)


def upgrade():
    connection = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Creates every missing application table, including all its model columns,
    # constraints, and indexes, without replacing existing tables or rows.
    Base.metadata.create_all(bind=connection, checkfirst=True)
    _add_missing_columns(connection)

    # Preserve the meaning of the legacy conversation archive flag.
    inspector = inspect(connection)
    if "conversations" in inspector.get_table_names():
        conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
        if {"is_archived", "is_active"}.issubset(conversation_columns):
            connection.execute(text("UPDATE conversations SET is_active = NOT is_archived"))

    # Legacy tables recorded created_at but not updated_at. Preserve their
    # timestamps rather than assigning the migration time to old records.
    for table_name in ("document_chunks", "messages"):
        if table_name in inspector.get_table_names():
            names = {column["name"] for column in inspector.get_columns(table_name)}
            if {"created_at", "updated_at"}.issubset(names):
                quoted_table = connection.dialect.identifier_preparer.quote(table_name)
                connection.execute(text(f"UPDATE {quoted_table} SET updated_at = created_at"))

    # create_all skips indexes when a table already existed.
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=connection, checkfirst=True)


def downgrade():
    # Keep the baseline migration non-destructive; never drop user data here.
    pass

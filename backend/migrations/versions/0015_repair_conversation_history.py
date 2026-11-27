"""Repair conversation columns on older/drifted deployments and index history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None

def upgrade():
    inspector = inspect(op.get_bind())
    if 'conversations' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('conversations')}
    if 'document_id' not in columns:
        op.add_column('conversations', sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=True))
        columns.add('document_id')
    if 'scope_type' not in columns:
        op.add_column('conversations', sa.Column('scope_type', sa.String(20), nullable=False, server_default='document'))
        columns.add('scope_type')
    if 'is_archived' not in columns:
        op.add_column('conversations', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.false()))
        columns.add('is_archived')
    if 'is_pinned' not in columns:
        op.add_column('conversations', sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.false()))
    foreign_keys = inspect(op.get_bind()).get_foreign_keys('conversations')
    if not any(fk.get('constrained_columns') == ['document_id'] and fk.get('referred_table') == 'documents' for fk in foreign_keys):
        op.create_foreign_key('fk_conversations_document_id_documents', 'conversations', 'documents', ['document_id'], ['id'], ondelete='SET NULL')
    indexes = {item['name'] for item in inspect(op.get_bind()).get_indexes('conversations')}
    if 'ix_conversations_document_id' not in indexes:
        op.create_index('ix_conversations_document_id', 'conversations', ['document_id'])
    if 'ix_conversations_user_pin_created' not in indexes:
        op.create_index('ix_conversations_user_pin_created', 'conversations', ['user_id', 'is_pinned', 'created_at'])

def downgrade():
    op.drop_index('ix_conversations_user_pin_created', table_name='conversations')

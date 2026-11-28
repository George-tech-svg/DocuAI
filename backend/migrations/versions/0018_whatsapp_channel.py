"""Add WhatsApp account links, message inbox, consent and usage ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('whatsapp_links',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('phone_e164', sa.String(20), nullable=False), sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('opted_in_at', sa.DateTime(timezone=True)), sa.Column('opted_out_at', sa.DateTime(timezone=True)),
        sa.Column('consent_source', sa.String(40)), sa.Column('last_inbound_at', sa.DateTime(timezone=True)),
        sa.Column('last_used_knowledge_base_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('knowledge_bases.id', ondelete='SET NULL')),
        sa.Column('last_scope_type', sa.String(20), nullable=False, server_default='folder'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('uq_whatsapp_links_active_phone', 'whatsapp_links', ['phone_e164'], unique=True, postgresql_where=sa.text('active IS TRUE'))
    op.create_index('ix_whatsapp_links_phone_e164', 'whatsapp_links', ['phone_e164'])
    op.create_table('whatsapp_link_challenges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone_e164', sa.String(20), nullable=False), sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consumed_at', sa.DateTime(timezone=True)), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, cols in [('ix_whatsapp_link_challenges_user_id',['user_id']),('ix_whatsapp_link_challenges_phone_e164',['phone_e164']),('ix_whatsapp_link_challenges_expires_at',['expires_at'])]: op.create_index(name,'whatsapp_link_challenges',cols)
    op.create_table('whatsapp_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True), sa.Column('provider_message_id', sa.String(180)),
        sa.Column('webhook_id', sa.String(180), unique=True), sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('phone_e164', sa.String(20), nullable=False), sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False, server_default='text'), sa.Column('text', sa.Text()),
        sa.Column('media_id', sa.String(180)), sa.Column('media_mime_type', sa.String(120)),
        sa.Column('provider_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default='received'), sa.Column('error', sa.Text()), sa.Column('response_text', sa.Text()),
        sa.Column('related_inbound_message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('whatsapp_messages.id', ondelete='SET NULL')),
        sa.Column('idempotency_key', sa.String(180), nullable=False, unique=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('provider_message_id', name='uq_whatsapp_provider_message'))
    for name, cols in [('ix_whatsapp_messages_provider_message_id',['provider_message_id']),('ix_whatsapp_messages_user_id',['user_id']),('ix_whatsapp_messages_phone_e164',['phone_e164']),('ix_whatsapp_messages_created_at',['created_at'])]: op.create_index(name,'whatsapp_messages',cols)
    op.create_table('whatsapp_consent_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True), sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('phone_e164', sa.String(20), nullable=False), sa.Column('action', sa.String(20), nullable=False),
        sa.Column('source', sa.String(40), nullable=False), sa.Column('provider_message_id', sa.String(180)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, cols in [('ix_whatsapp_consent_events_user_id',['user_id']),('ix_whatsapp_consent_events_phone_e164',['phone_e164']),('ix_whatsapp_consent_events_created_at',['created_at'])]: op.create_index(name,'whatsapp_consent_events',cols)
    op.add_column('whatsapp_messages', sa.Column('response_offset', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('message_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('whatsapp_message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('whatsapp_messages.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('provider_message_id', sa.String(180)), sa.Column('units', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('cost_amount', sa.Numeric(12,6)), sa.Column('currency', sa.String(8)),
        sa.Column('cost_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, cols in [('ix_message_usage_whatsapp_message_id',['whatsapp_message_id']),('ix_message_usage_user_id',['user_id']),('ix_message_usage_provider_message_id',['provider_message_id'])]: op.create_index(name,'message_usage',cols)
    op.create_table('whatsapp_document_uploads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('inbound_message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('whatsapp_messages.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('notified_at', sa.DateTime(timezone=True)), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for name, cols in [('ix_whatsapp_document_uploads_document_id',['document_id']),('ix_whatsapp_document_uploads_inbound_message_id',['inbound_message_id']),('ix_whatsapp_document_uploads_user_id',['user_id'])]: op.create_index(name,'whatsapp_document_uploads',cols)
    op.execute("CREATE FUNCTION prevent_whatsapp_consent_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'whatsapp_consent_events are append-only'; END; $$ LANGUAGE plpgsql")
    op.execute('CREATE TRIGGER trg_whatsapp_consent_append_only BEFORE UPDATE OR DELETE ON whatsapp_consent_events FOR EACH ROW EXECUTE FUNCTION prevent_whatsapp_consent_mutation()')

def downgrade():
    op.execute('DROP TRIGGER trg_whatsapp_consent_append_only ON whatsapp_consent_events')
    op.execute('DROP FUNCTION prevent_whatsapp_consent_mutation()')
    op.drop_column('whatsapp_messages', 'response_offset')
    for table in ('whatsapp_document_uploads','message_usage','whatsapp_consent_events','whatsapp_messages','whatsapp_link_challenges','whatsapp_links'):
        op.drop_table(table)

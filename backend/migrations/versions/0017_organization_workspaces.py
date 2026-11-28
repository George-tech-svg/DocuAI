"""Add organizations, memberships, shared conversation metadata and billing."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('type', sa.String(30), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('business','school','sacco','ngo','law_firm','other')", name='ck_organizations_type'),
    )
    op.create_index('ix_organizations_created_by', 'organizations', ['created_by'])
    op.create_table('organization_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='member'),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_organization_member'),
        sa.CheckConstraint("role IN ('owner','admin','member','viewer')", name='ck_organization_member_role'),
    )
    op.create_index('ix_organization_members_organization_id', 'organization_members', ['organization_id'])
    op.create_index('ix_organization_members_user_id', 'organization_members', ['user_id'])
    op.create_index('ix_organization_members_user_role', 'organization_members', ['user_id', 'role'])
    op.create_table('organization_invites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='member'),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('invited_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('admin','member','viewer')", name='ck_organization_invite_role'),
        sa.CheckConstraint("status IN ('pending','accepted','expired','revoked')", name='ck_organization_invite_status'),
    )
    op.create_index('ix_organization_invites_organization_id', 'organization_invites', ['organization_id'])
    op.create_index('ix_organization_invites_email', 'organization_invites', ['email'])
    op.create_index('ix_organization_invites_token_hash', 'organization_invites', ['token_hash'])
    op.create_index('ix_organization_invites_expires_at', 'organization_invites', ['expires_at'])
    op.create_index('ix_organization_invites_status', 'organization_invites', ['status'])
    op.create_table('audit_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(80), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_audit_events_organization_id', 'audit_events', ['organization_id'])
    op.create_index('ix_audit_events_actor_user_id', 'audit_events', ['actor_user_id'])
    op.create_index('ix_audit_events_action', 'audit_events', ['action'])
    op.create_index('ix_audit_events_created_at', 'audit_events', ['created_at'])
    op.execute("""CREATE FUNCTION prevent_audit_event_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'audit_events are append-only'; END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER trg_audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation()")

    op.add_column('knowledge_bases', sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_knowledge_bases_organization_id', 'knowledge_bases', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_knowledge_bases_organization_id', 'knowledge_bases', ['organization_id'])
    op.add_column('documents', sa.Column('uploaded_by_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_documents_uploaded_by_user_id', 'documents', 'users', ['uploaded_by_user_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_documents_uploaded_by_user_id', 'documents', ['uploaded_by_user_id'])
    op.add_column('conversations', sa.Column('visibility', sa.String(12), nullable=False, server_default='private'))
    op.create_check_constraint('ck_conversations_visibility', 'conversations', "visibility IN ('private','shared')")
    op.add_column('messages', sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_messages_actor_user_id', 'messages', 'users', ['actor_user_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_messages_actor_user_id', 'messages', ['actor_user_id'])
    op.add_column('subscriptions', sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('subscriptions', sa.Column('seat_limit', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_subscriptions_organization_id', 'subscriptions', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_subscriptions_organization_id', 'subscriptions', ['organization_id'])
    op.create_check_constraint('ck_subscriptions_seat_limit', 'subscriptions', 'seat_limit IS NULL OR seat_limit > 0')
    op.add_column('document_events', sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_document_events_organization_id', 'document_events', 'organizations', ['organization_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_document_events_organization_id', 'document_events', ['organization_id'])

def downgrade():
    op.drop_index('ix_document_events_organization_id', table_name='document_events')
    op.drop_constraint('fk_document_events_organization_id', 'document_events', type_='foreignkey')
    op.drop_column('document_events', 'organization_id')
    op.drop_constraint('ck_subscriptions_seat_limit', 'subscriptions', type_='check')
    op.drop_index('ix_subscriptions_organization_id', table_name='subscriptions')
    op.drop_constraint('fk_subscriptions_organization_id', 'subscriptions', type_='foreignkey')
    op.drop_column('subscriptions', 'seat_limit')
    op.drop_column('subscriptions', 'organization_id')
    op.drop_index('ix_messages_actor_user_id', table_name='messages')
    op.drop_constraint('fk_messages_actor_user_id', 'messages', type_='foreignkey')
    op.drop_column('messages', 'actor_user_id')
    op.drop_constraint('ck_conversations_visibility', 'conversations', type_='check')
    op.drop_column('conversations', 'visibility')
    op.drop_index('ix_documents_uploaded_by_user_id', table_name='documents')
    op.drop_constraint('fk_documents_uploaded_by_user_id', 'documents', type_='foreignkey')
    op.drop_column('documents', 'uploaded_by_user_id')
    op.drop_index('ix_knowledge_bases_organization_id', table_name='knowledge_bases')
    op.drop_constraint('fk_knowledge_bases_organization_id', 'knowledge_bases', type_='foreignkey')
    op.drop_column('knowledge_bases', 'organization_id')
    op.execute('DROP TRIGGER trg_audit_events_append_only ON audit_events')
    op.execute('DROP FUNCTION prevent_audit_event_mutation()')
    for index in ('ix_audit_events_created_at','ix_audit_events_action','ix_audit_events_actor_user_id','ix_audit_events_organization_id'):
        op.drop_index(index, table_name='audit_events')
    op.drop_table('audit_events')
    for index in ('ix_organization_invites_status','ix_organization_invites_expires_at','ix_organization_invites_token_hash','ix_organization_invites_email','ix_organization_invites_organization_id'):
        op.drop_index(index, table_name='organization_invites')
    op.drop_table('organization_invites')
    for index in ('ix_organization_members_user_role','ix_organization_members_user_id','ix_organization_members_organization_id'):
        op.drop_index(index, table_name='organization_members')
    op.drop_table('organization_members')
    op.drop_index('ix_organizations_created_by', table_name='organizations')
    op.drop_table('organizations')

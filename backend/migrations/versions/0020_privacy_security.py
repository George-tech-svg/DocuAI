"""Add privacy controls, export/deletion queues, and security state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('admin_totp_secret', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('admin_totp_enabled', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('knowledge_bases', sa.Column('is_sensitive', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('organizations', sa.Column('retention_days', sa.Integer(), nullable=True))
    op.create_check_constraint('ck_organizations_retention_days', 'organizations', 'retention_days IS NULL OR retention_days BETWEEN 1 AND 3650')
    # Audit identifiers remain useful as historical references after account
    # and payment-recovery records are erased; FKs would attempt an UPDATE and
    # conflict with the append-only trigger below.
    op.execute('ALTER TABLE admin_audit_logs DROP CONSTRAINT IF EXISTS admin_audit_logs_admin_user_id_fkey')
    op.execute('ALTER TABLE admin_audit_logs DROP CONSTRAINT IF EXISTS admin_audit_logs_payment_recovery_request_id_fkey')

    op.create_table('privacy_consents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('policy', sa.String(30), nullable=False), sa.Column('version', sa.String(40), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'policy', 'version', name='uq_privacy_consent_user_policy_version'),
        sa.CheckConstraint("policy IN ('terms','privacy')", name='ck_privacy_consents_policy'))
    op.create_index('ix_privacy_consents_user_id', 'privacy_consents', ['user_id'])

    op.create_table('security_counters',
        sa.Column('bucket_hash', sa.String(64), primary_key=True), sa.Column('scope', sa.String(40), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('locked_until', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_security_counters_scope', 'security_counters', ['scope'])

    op.create_table('data_export_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('owner_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True)),
        sa.Column('requested_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('storage_public_id', sa.String(500)), sa.Column('error', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)), sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('queued','processing','ready','failed','expired')", name='ck_data_export_requests_status'))
    for name, cols in [('ix_data_export_requests_owner_user_id',['owner_user_id']), ('ix_data_export_requests_organization_id',['organization_id']), ('ix_data_export_requests_requested_by_user_id',['requested_by_user_id']), ('ix_data_export_requests_status',['status'])]:
        op.create_index(name, 'data_export_requests', cols)

    op.create_table('data_deletion_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('target_type', sa.String(20), nullable=False), sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requested_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'), sa.Column('error', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("target_type IN ('account','organization')", name='ck_data_deletion_requests_target_type'),
        sa.CheckConstraint("status IN ('queued','processing','done','failed')", name='ck_data_deletion_requests_status'))
    for name, cols in [('ix_data_deletion_requests_target_id',['target_id']), ('ix_data_deletion_requests_requested_by_user_id',['requested_by_user_id']), ('ix_data_deletion_requests_status',['status'])]:
        op.create_index(name, 'data_deletion_requests', cols)

    # Keep both platform-admin and organization audit records append-only.
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_audit_row_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'audit records are append-only'; END;
    $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_admin_audit_append_only ON admin_audit_logs")
    op.execute("CREATE TRIGGER trg_admin_audit_append_only BEFORE UPDATE OR DELETE ON admin_audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_audit_row_mutation()")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_append_only ON audit_events")
    op.execute("CREATE TRIGGER trg_audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION prevent_audit_row_mutation()")


def downgrade():
    op.execute('DROP TRIGGER IF EXISTS trg_audit_events_append_only ON audit_events')
    op.execute('DROP TRIGGER IF EXISTS trg_admin_audit_append_only ON admin_audit_logs')
    op.execute('DROP FUNCTION IF EXISTS prevent_audit_row_mutation()')
    for table, names in [('data_deletion_requests',['ix_data_deletion_requests_status','ix_data_deletion_requests_requested_by_user_id','ix_data_deletion_requests_target_id']), ('data_export_requests',['ix_data_export_requests_status','ix_data_export_requests_requested_by_user_id','ix_data_export_requests_organization_id','ix_data_export_requests_owner_user_id'])]:
        for name in names: op.drop_index(name, table_name=table)
    op.drop_table('data_deletion_requests')
    op.drop_table('data_export_requests')
    op.drop_index('ix_security_counters_scope', table_name='security_counters')
    op.drop_table('security_counters')
    op.drop_index('ix_privacy_consents_user_id', table_name='privacy_consents')
    op.drop_table('privacy_consents')
    op.drop_constraint('ck_organizations_retention_days', 'organizations', type_='check')
    op.drop_column('organizations', 'retention_days')
    op.drop_column('knowledge_bases', 'is_sensitive')
    op.drop_column('users', 'admin_totp_enabled')
    op.drop_column('users', 'admin_totp_secret')

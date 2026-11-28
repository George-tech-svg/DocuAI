"""Add structured business tools, company vault, receipts, and payroll rates."""
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('knowledge_bases', sa.Column('kind', sa.String(30), nullable=False, server_default='standard'))
    op.create_check_constraint('ck_knowledge_bases_kind', 'knowledge_bases', "kind IN ('standard','company_vault')")

    op.create_table('business_tool_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL')),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE')),
        sa.Column('tool_type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='suggested'),
        sa.Column('output_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('sources_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('confirmed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("tool_type IN ('kra_notice','tender','receipt')", name='ck_business_tool_runs_type'),
        sa.CheckConstraint("status IN ('suggested','confirmed','dismissed')", name='ck_business_tool_runs_status'))
    op.create_index('ix_business_tool_runs_user_id', 'business_tool_runs', ['user_id'])
    op.create_index('ix_business_tool_runs_organization_id', 'business_tool_runs', ['organization_id'])
    op.create_index('ix_business_tool_runs_document_id', 'business_tool_runs', ['document_id'])
    op.create_index('ix_business_tool_runs_tool_type', 'business_tool_runs', ['tool_type'])
    op.create_index('ix_business_tool_runs_status', 'business_tool_runs', ['status'])

    op.create_table('company_vault_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE')),
        sa.Column('category', sa.String(80), nullable=False, server_default='other'),
        sa.Column('display_name', sa.String(220), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_company_vault_items_document_id', 'company_vault_items', ['document_id'])
    op.create_index('ix_company_vault_items_user_id', 'company_vault_items', ['user_id'])
    op.create_index('ix_company_vault_items_organization_id', 'company_vault_items', ['organization_id'])
    op.create_index('ix_company_vault_items_expires_at', 'company_vault_items', ['expires_at'])

    op.create_table('business_receipts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tool_run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('business_tool_runs.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE')),
        sa.Column('source_document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='SET NULL')),
        sa.Column('supplier', sa.String(220)), sa.Column('supplier_pin', sa.String(40)),
        sa.Column('receipt_date', sa.DateTime(timezone=True)),
        sa.Column('line_items', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('vat_amount', sa.Numeric(14, 2)), sa.Column('total_amount', sa.Numeric(14, 2)),
        sa.Column('payment_method', sa.String(80)),
        sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_business_receipts_tool_run_id', 'business_receipts', ['tool_run_id'])
    op.create_index('ix_business_receipts_user_id', 'business_receipts', ['user_id'])
    op.create_index('ix_business_receipts_organization_id', 'business_receipts', ['organization_id'])
    op.create_index('ix_business_receipts_fingerprint', 'business_receipts', ['fingerprint'])

    op.create_table('payroll_rates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(60), nullable=False),
        sa.Column('display_name', sa.String(160), nullable=False),
        sa.Column('rate_value', sa.Numeric(12, 6)),
        sa.Column('rate_kind', sa.String(16), nullable=False, server_default='percentage'),
        sa.Column('tolerance_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('effective_from', sa.DateTime(timezone=True)), sa.Column('effective_to', sa.DateTime(timezone=True)),
        sa.Column('source_url', sa.Text()), sa.Column('notes', sa.Text()),
        sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('code','effective_from',name='uq_payroll_rate_code_start'),
        sa.CheckConstraint("rate_kind IN ('percentage','fixed')", name='ck_payroll_rates_kind'),
        sa.CheckConstraint('rate_value IS NULL OR rate_value >= 0', name='ck_payroll_rates_nonnegative'),
        sa.CheckConstraint('effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from', name='ck_payroll_rates_dates'),
        sa.CheckConstraint('tolerance_amount >= 0', name='ck_payroll_rates_tolerance'))
    op.create_index('ix_payroll_rates_code', 'payroll_rates', ['code'])

    # Empty, non-operative entries only: the platform operator must supply the
    # applicable name, value, effective dates, and official source.
    now = datetime.now(timezone.utc)
    placeholders = [{'id': uuid4(), 'code': f'placeholder_{n}', 'display_name': f'Add statutory item {n}',
        'rate_value': None, 'rate_kind': 'percentage', 'tolerance_amount': 0,
        'effective_from': None, 'effective_to': None, 'source_url': None, 'notes': None,
        'created_at': now, 'updated_at': now} for n in range(1, 5)]
    payroll = sa.table('payroll_rates', sa.column('id', postgresql.UUID(as_uuid=True)),
        sa.column('code', sa.String), sa.column('display_name', sa.String), sa.column('rate_value', sa.Numeric),
        sa.column('rate_kind', sa.String), sa.column('tolerance_amount', sa.Numeric),
        sa.column('effective_from', sa.DateTime(timezone=True)), sa.column('effective_to', sa.DateTime(timezone=True)),
        sa.column('source_url', sa.Text), sa.column('notes', sa.Text), sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)))
    op.bulk_insert(payroll, placeholders)


def downgrade():
    op.drop_index('ix_payroll_rates_code', table_name='payroll_rates')
    op.drop_table('payroll_rates')
    for name in ('ix_business_receipts_fingerprint','ix_business_receipts_organization_id','ix_business_receipts_user_id','ix_business_receipts_tool_run_id'):
        op.drop_index(name, table_name='business_receipts')
    op.drop_table('business_receipts')
    for name in ('ix_company_vault_items_expires_at','ix_company_vault_items_organization_id','ix_company_vault_items_user_id','ix_company_vault_items_document_id'):
        op.drop_index(name, table_name='company_vault_items')
    op.drop_table('company_vault_items')
    for name in ('ix_business_tool_runs_status','ix_business_tool_runs_tool_type','ix_business_tool_runs_document_id','ix_business_tool_runs_organization_id','ix_business_tool_runs_user_id'):
        op.drop_index(name, table_name='business_tool_runs')
    op.drop_table('business_tool_runs')
    op.drop_constraint('ck_knowledge_bases_kind', 'knowledge_bases', type_='check')
    op.drop_column('knowledge_bases', 'kind')

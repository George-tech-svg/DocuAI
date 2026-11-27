"""Add document event extraction and reminder delivery."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('document_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('kind', sa.String(30), nullable=False, server_default='other'),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('source_excerpt', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='suggested'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_document_events_document_id', 'document_events', ['document_id'])
    op.create_index('ix_document_events_user_id', 'document_events', ['user_id'])
    op.create_index('ix_document_events_due_at', 'document_events', ['due_at'])
    op.create_index('ix_document_events_status', 'document_events', ['status'])
    op.create_index('ix_document_events_user_due', 'document_events', ['user_id', 'due_at'])
    op.create_table('notification_preferences',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('channels', postgresql.JSONB(), nullable=False, server_default=sa.text("'{\"email\": true, \"in_app\": true}'::jsonb")),
        sa.Column('lead_days', postgresql.JSONB(), nullable=False, server_default=sa.text("'[14, 7, 1]'::jsonb")),
        sa.Column('quiet_start', sa.String(5), nullable=True),
        sa.Column('quiet_end', sa.String(5), nullable=True),
        sa.Column('timezone', sa.String(80), nullable=False, server_default='Africa/Nairobi'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table('reminders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('document_events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('remind_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='scheduled'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('event_id', 'channel', 'remind_at', name='uq_reminder_event_channel_time'),
    )
    for col in ('event_id', 'user_id', 'remind_at', 'status'):
        op.create_index(f'ix_reminders_{col}', 'reminders', [col])
    op.create_index('ix_reminders_status_time', 'reminders', ['status', 'remind_at'])

def downgrade():
    op.drop_table('reminders')
    op.drop_table('notification_preferences')
    op.drop_table('document_events')

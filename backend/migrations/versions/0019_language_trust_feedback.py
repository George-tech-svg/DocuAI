"""Add answer-language preferences and durable answer feedback/reports."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('answer_language', sa.String(8), nullable=False, server_default='auto'))
    op.create_check_constraint('ck_users_answer_language', 'users', "answer_language IN ('auto','en','sw')")
    op.create_table('answer_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assistant_message_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('messages.id', ondelete='SET NULL')),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='SET NULL')),
        sa.Column('question', sa.Text(), nullable=False), sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('sources_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('model_version', sa.String(100), nullable=False), sa.Column('rating', sa.String(12), nullable=False),
        sa.Column('comment', sa.Text()), sa.Column('status', sa.String(16), nullable=False, server_default='new'),
        sa.Column('reviewed_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('review_note', sa.Text()), sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id','assistant_message_id',name='uq_answer_feedback_user_message'),
        sa.CheckConstraint("rating IN ('up','down','report')", name='ck_answer_feedback_rating'),
        sa.CheckConstraint("status IN ('new','reviewed','resolved')", name='ck_answer_feedback_status'))
    for name, table, cols in [
        ('ix_answer_feedback_user_id','answer_feedback',['user_id']),
        ('ix_answer_feedback_assistant_message_id','answer_feedback',['assistant_message_id']),
        ('ix_answer_feedback_conversation_id','answer_feedback',['conversation_id']),
        ('ix_answer_feedback_rating','answer_feedback',['rating']),
        ('ix_answer_feedback_status','answer_feedback',['status']),
        ('ix_answer_feedback_created_at','answer_feedback',['created_at']),
        ('ix_answer_feedback_status_created','answer_feedback',['status','created_at']),
    ]: op.create_index(name,table,cols)

def downgrade():
    for name in ('ix_answer_feedback_status_created','ix_answer_feedback_created_at','ix_answer_feedback_status','ix_answer_feedback_rating','ix_answer_feedback_conversation_id','ix_answer_feedback_assistant_message_id','ix_answer_feedback_user_id'):
        op.drop_index(name, table_name='answer_feedback')
    op.drop_table('answer_feedback')
    op.drop_constraint('ck_users_answer_language','users',type_='check')
    op.drop_column('users','answer_language')

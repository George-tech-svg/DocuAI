"""Add the shared, versioned Kenyan reference library."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('library_collections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('category', sa.String(40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("category IN ('tax','employment','procurement','companies','data-protection','education','courts')", name='ck_library_collection_category'),
    )
    op.create_index('ix_library_collections_slug', 'library_collections', ['slug'])
    op.create_index('ix_library_collections_category', 'library_collections', ['category'])
    op.create_table('library_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('collection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('library_collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('short_name', sa.String(160), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=True),
        sa.Column('storage_url', sa.Text(), nullable=True),
        sa.Column('cloudinary_public_id', sa.String(500), nullable=True),
        sa.Column('cloudinary_resource_type', sa.String(30), nullable=True),
        sa.Column('publisher', sa.String(200), nullable=False),
        sa.Column('document_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version_label', sa.String(120), nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('ocr_used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('ocr_confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('collection_id', 'short_name', 'content_hash', name='uq_library_doc_version_hash'),
    )
    op.create_index('ix_library_documents_collection_id', 'library_documents', ['collection_id'])
    op.create_index('ix_library_documents_short_name', 'library_documents', ['short_name'])
    op.create_index('ix_library_documents_is_current', 'library_documents', ['is_current'])
    op.create_index('ix_library_documents_content_hash', 'library_documents', ['content_hash'])
    op.create_index('ix_library_documents_status', 'library_documents', ['status'])
    op.create_index('ix_library_documents_current', 'library_documents', ['collection_id', 'short_name', 'is_current'])
    op.create_index('uq_library_one_current_version', 'library_documents', ['collection_id', 'short_name'], unique=True, postgresql_where=sa.text('is_current = true'))
    op.create_table('library_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('library_document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('library_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('section_title', sa.String(180), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_library_chunks_library_document_id', 'library_chunks', ['library_document_id'])
    op.execute("CREATE INDEX ix_library_chunks_content_fts ON library_chunks USING GIN (to_tsvector('simple', content))")
    op.create_table('library_updates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('collection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('library_collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('previous_document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('library_documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('new_document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('library_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('change_kind', sa.String(20), nullable=False, server_default='added'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_library_updates_collection_id', 'library_updates', ['collection_id'])
    op.create_index('ix_library_updates_new_document_id', 'library_updates', ['new_document_id'])
    op.create_index('ix_library_updates_created_at', 'library_updates', ['created_at'])
    op.add_column('conversations', sa.Column('library_collection_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_conversations_library_collection_id_library_collections', 'conversations', 'library_collections', ['library_collection_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_conversations_library_collection_id', 'conversations', ['library_collection_id'])

def downgrade():
    op.drop_index('ix_conversations_library_collection_id', table_name='conversations')
    op.drop_constraint('fk_conversations_library_collection_id_library_collections', 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'library_collection_id')
    op.drop_table('library_updates')
    op.drop_index('ix_library_chunks_content_fts', table_name='library_chunks')
    op.drop_table('library_chunks')
    op.drop_index('uq_library_one_current_version', table_name='library_documents')
    op.drop_table('library_documents')
    op.drop_table('library_collections')

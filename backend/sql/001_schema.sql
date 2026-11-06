-- ONLY FOR A NEW EMPTY DATABASE. DO NOT APPLY TO AN EXISTING NEON DATABASE WITHOUT REVIEW.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE users (
 id UUID PRIMARY KEY, full_name VARCHAR(150) NOT NULL, email VARCHAR(255) NOT NULL UNIQUE,
 password_hash VARCHAR(255) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE,
 is_verified BOOLEAN NOT NULL DEFAULT FALSE, is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE knowledge_bases (
 id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name VARCHAR(150) NOT NULL, description TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE documents (
 id UUID PRIMARY KEY, knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
 original_filename VARCHAR(255) NOT NULL, content_type VARCHAR(150) NOT NULL,
 file_size_bytes BIGINT NOT NULL, cloudinary_public_id VARCHAR(500), cloudinary_resource_type VARCHAR(30),
 storage_url TEXT, status VARCHAR(10) NOT NULL DEFAULT 'pending', page_count INTEGER,
 chunk_count INTEGER NOT NULL DEFAULT 0, processing_error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), processed_at TIMESTAMPTZ
);
CREATE TABLE document_chunks (
 id UUID PRIMARY KEY, document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 chunk_index INTEGER NOT NULL, page_number INTEGER, content TEXT NOT NULL, embedding VECTOR(384) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE conversations (
 id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
 title VARCHAR(255) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE messages (
 id UUID PRIMARY KEY, conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 role VARCHAR(20) NOT NULL, content TEXT NOT NULL, sources_json TEXT, token_count INTEGER,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 model_name VARCHAR(100), is_error BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_kb_user ON knowledge_bases(user_id);
CREATE INDEX idx_docs_kb ON documents(knowledge_base_id);
CREATE INDEX idx_chunks_doc ON document_chunks(document_id);
CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);

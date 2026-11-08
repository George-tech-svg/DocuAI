"""Find the closest document passages using pgvector similarity."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.document_chunk import DocumentChunk
from app.models.document import Document
from app.services.embeddings import embed_texts

def retrieve(db: Session, kb_id, question: str, limit: int=5, query_vector=None, document_id=None):
    """Retrieve the most relevant passages from a knowledge base."""
    if query_vector is None:
        query_vector = embed_texts([question])[0]
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    statement = select(DocumentChunk, Document.original_filename, Document.id).join(Document, Document.id == DocumentChunk.document_id).where(Document.knowledge_base_id == kb_id, Document.status == 'ready')
    if document_id is not None:
        statement = statement.where(Document.id == document_id)
    statement = statement.order_by(distance).limit(limit)
    return db.execute(statement).all()

"""Hybrid keyword and vector retrieval for indexed document passages."""

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session
from app.models.document_chunk import DocumentChunk
from app.models.document import Document
from app.services.embeddings import embed_texts


def retrieve(db: Session, kb_id, question: str, limit: int = 5, query_vector=None, document_id=None):
    """Fuse semantic and PostgreSQL full-text rankings within the requested scope."""
    if query_vector is None:
        query_vector = embed_texts([question])[0]

    base = select(DocumentChunk, Document.original_filename, Document.id).join(
        Document, Document.id == DocumentChunk.document_id
    ).where(
        Document.knowledge_base_id == kb_id,
        Document.status == 'ready',
    )
    if document_id is not None:
        base = base.where(Document.id == document_id)

    candidate_limit = max(limit * 4, 20)
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    vector_hits = db.execute(base.order_by(distance).limit(candidate_limit)).all()

    text_vector = func.to_tsvector(literal_column("'simple'"), DocumentChunk.content)
    text_query = func.websearch_to_tsquery(literal_column("'simple'"), question)
    keyword_hits = db.execute(
        base.where(text_vector.op("@@")(text_query))
        .order_by(func.ts_rank_cd(text_vector, text_query).desc())
        .limit(candidate_limit)
    ).all()

    # If the query has no lexical match, preserve the existing vector search order.
    if not keyword_hits:
        return vector_hits[:limit], {
            'path': 'vector-only',
            'vector_candidates': len(vector_hits),
            'keyword_candidates': 0,
            'vector_top_five': min(limit, len(vector_hits)),
            'keyword_top_five': 0,
        }

    # Reciprocal-rank fusion combines rankings with different score scales.
    # Candidate rows from both searches are deduplicated by chunk ID.
    rrf_constant = 60
    fused = {}
    for rank, hit in enumerate(vector_hits, start=1):
        chunk = hit[0]
        chunk_id = chunk.id
        entry = fused.setdefault(chunk_id, {'hit': hit, 'score': 0.0, 'vector': False, 'keyword': False})
        entry['score'] += 1 / (rrf_constant + rank)
        entry['vector'] = True
    for rank, hit in enumerate(keyword_hits, start=1):
        chunk = hit[0]
        chunk_id = chunk.id
        entry = fused.setdefault(chunk_id, {'hit': hit, 'score': 0.0, 'vector': False, 'keyword': False})
        entry['score'] += 1 / (rrf_constant + rank)
        entry['keyword'] = True

    ranked = sorted(fused.values(), key=lambda entry: entry['score'], reverse=True)
    top_hits = [entry['hit'] for entry in ranked[:limit]]
    top_five = ranked[:limit]
    return top_hits, {
        'path': 'hybrid',
        'vector_candidates': len(vector_hits),
        'keyword_candidates': len(keyword_hits),
        'vector_top_five': sum(entry['vector'] for entry in top_five),
        'keyword_top_five': sum(entry['keyword'] for entry in top_five),
    }

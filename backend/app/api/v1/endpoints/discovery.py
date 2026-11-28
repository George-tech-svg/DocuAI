"""Search files and saved chats across the signed-in user's workspaces."""

from __future__ import annotations

import math
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, subscribed_user
from app.db.session import get_db
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.entities import (
    LibraryChunk,
    LibraryCollection,
    LibraryDocument,
    Message,
    Organization,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.chat import Source
from app.services.embeddings import embed_texts
from app.services.knowledge_base_service import list_knowledge_bases
from app.services.language import requested_language
from app.services.security_controls import enforce_rate_limit
from app.services.trusted_answers import trusted_answer
from app.services.user_guide import GUIDE_CONTEXT, GUIDE_PASSAGES

router = APIRouter(tags=["Search and help"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    kind: Literal["all", "files", "chats"] = "all"
    folder_id: UUID | None = None


class HelpRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1500)


SEARCH_STOPWORDS = {
    "a", "about", "all", "and", "can", "could", "document", "documents", "file", "files",
    "find", "for", "from", "in", "is", "it", "look", "me", "my", "of", "on", "or", "please",
    "search", "show", "tell", "that", "the", "this", "through", "to", "what", "which", "where",
    "with", "you", "your", "chat", "chats", "history", "conversation", "conversations", "old", "past",
    "contains", "containing", "include", "includes", "mentioned", "mentions", "said", "says",
}


def _search_text_query(query: str):
    terms = _search_terms(query)
    if not terms:
        return func.websearch_to_tsquery(literal_column("'simple'"), query)
    # Terms are restricted to letters, numbers, and underscores before being
    # joined, so user input cannot add operators or change the SQL expression.
    expression = " | ".join(f"{word}:*" for word in terms[:24])
    return func.to_tsquery(literal_column("'simple'"), expression)


def _search_terms(query: str) -> list[str]:
    return [word for word in re.findall(r"[\w]+", query.lower()) if len(word) > 1 and word not in SEARCH_STOPWORDS]


def _meaning_search_text(query: str) -> str:
    terms = _search_terms(query)
    return " ".join(terms) or query


def _like_query(query: str) -> str:
    return "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _rrf_add(scores: dict, key, rank: int, amount: float = 1.0):
    entry = scores.setdefault(key, {"score": 0.0})
    entry["score"] += amount / (60 + rank)
    return entry


def _search_files(db: Session, user: User, query: str, folder_id: UUID | None, query_vector: list[float]):
    folders = list_knowledge_bases(db, user.id)
    folder_map = {folder.id: folder for folder in folders}
    allowed_ids = list(folder_map)
    if folder_id:
        allowed_ids = [folder_id] if folder_id in folder_map else []
    hits = {}
    if allowed_ids:
        base = (
            select(DocumentChunk, Document, KnowledgeBase, Organization.name)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .outerjoin(Organization, Organization.id == KnowledgeBase.organization_id)
            .where(Document.knowledge_base_id.in_(allowed_ids), Document.status == "ready")
        )
        vector_rows = db.execute(
            base.order_by(DocumentChunk.embedding.cosine_distance(query_vector)).limit(500)
        ).all()
        text_query = _search_text_query(query)
        # Match the indexed expression exactly so PostgreSQL can use the GIN index.
        searchable_text = func.to_tsvector(literal_column("'simple'"), DocumentChunk.content)
        keyword_rows = db.execute(
            base.where(searchable_text.op("@@")(text_query))
            .order_by(func.ts_rank_cd(searchable_text, text_query).desc())
            .limit(500)
        ).all()
        for rank, row in enumerate(vector_rows, 1):
            entry = _rrf_add(hits, row[1].id, rank)
            if "row" not in entry:
                entry.update(row=row, excerpt=row[0].content, page=row[0].page_number)
        for rank, row in enumerate(keyword_rows, 1):
            entry = _rrf_add(hits, row[1].id, rank)
            if "row" not in entry or len(row[0].content) > len(entry.get("excerpt", "")):
                entry.update(row=row, excerpt=row[0].content, page=row[0].page_number)

        title_terms = _search_terms(query) or [query.strip()]
        title_match = or_(*[
            Document.original_filename.ilike(_like_query(term), escape="\\")
            for term in title_terms[:12]
        ])
        title_rows = db.execute(
            select(Document, KnowledgeBase, Organization.name)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .outerjoin(Organization, Organization.id == KnowledgeBase.organization_id)
            .where(
                Document.knowledge_base_id.in_(allowed_ids),
                Document.status == "ready",
                title_match,
            )
            .order_by(Document.updated_at.desc())
            .limit(80)
        ).all()
        for rank, (document, kb, org_name) in enumerate(title_rows, 1):
            entry = _rrf_add(hits, document.id, rank, amount=2.0)
            existing_chunk = entry.get("row", (None,))[0]
            entry["row"] = (existing_chunk, document, kb, org_name)
            entry.setdefault("excerpt", "Matching file name")
            entry.setdefault("page", None)

    file_results = []
    for document_id, item in hits.items():
        chunk, document, kb, org_name = item["row"]
        folder = folder_map.get(kb.id)
        if folder is None:
            continue
        path = " / ".join(part for part in (org_name or "Personal folders", folder.name, document.original_filename) if part)
        file_results.append({
            "type": "file", "id": str(document.id), "file_id": str(document.id),
            "folder_id": str(kb.id), "folder_name": folder.name,
            "organization_id": str(kb.organization_id) if kb.organization_id else None,
            "organization_name": org_name, "path": path,
            "title": document.original_filename,
            "excerpt": (item.get("excerpt") or "Matching file name")[:420],
            "page_number": item.get("page"), "score": item["score"],
            "is_archived": document.is_archived,
        })
    file_results.sort(key=lambda item: item["score"], reverse=True)

    # Public reference documents use the same meaning based and keyword search,
    # but they are clearly labeled so users can tell them from their own files.
    library_hits = {}
    library_base = (
        select(LibraryChunk, LibraryDocument, LibraryCollection)
        .join(LibraryDocument, LibraryDocument.id == LibraryChunk.library_document_id)
        .join(LibraryCollection, LibraryCollection.id == LibraryDocument.collection_id)
        .where(LibraryDocument.status == "ready", LibraryDocument.is_current.is_(True))
    )
    library_vector_rows = db.execute(
        library_base.order_by(LibraryChunk.embedding.cosine_distance(query_vector)).limit(500)
    ).all()
    library_text_query = _search_text_query(query)
    # Keep this identical to the library content GIN index expression.
    library_search_text = func.to_tsvector(literal_column("'simple'"), LibraryChunk.content)
    library_keyword_rows = db.execute(
        library_base.where(library_search_text.op("@@")(library_text_query))
        .order_by(func.ts_rank_cd(library_search_text, library_text_query).desc())
        .limit(500)
    ).all()
    for rank, row in enumerate(library_vector_rows, 1):
        entry = _rrf_add(library_hits, row[1].id, rank)
        if "row" not in entry:
            entry.update(row=row, excerpt=row[0].content, page=row[0].page_number)
    for rank, row in enumerate(library_keyword_rows, 1):
        entry = _rrf_add(library_hits, row[1].id, rank)
        if "row" not in entry or len(row[0].content) > len(entry.get("excerpt", "")):
            entry.update(row=row, excerpt=row[0].content, page=row[0].page_number)
    library_title_match = or_(*[
        LibraryDocument.title.ilike(_like_query(term), escape="\\")
        for term in (_search_terms(query) or [query.strip()])[:12]
    ])
    library_title_rows = db.execute(
        select(LibraryDocument, LibraryCollection)
        .join(LibraryCollection, LibraryCollection.id == LibraryDocument.collection_id)
        .where(
            LibraryDocument.status == "ready",
            LibraryDocument.is_current.is_(True),
            library_title_match,
        )
        .order_by(LibraryDocument.title)
        .limit(80)
    ).all()
    for rank, (document, collection) in enumerate(library_title_rows, 1):
        entry = _rrf_add(library_hits, document.id, rank, amount=2.0)
        entry["row"] = (None, document, collection)
        entry.setdefault("excerpt", "Matching document title")
        entry.setdefault("page", None)
    library_results = []
    for item in library_hits.values():
        chunk, document, collection = item["row"]
        library_results.append({
            "type": "public_document", "id": str(document.id), "file_id": None,
            "folder_id": None, "folder_name": None, "organization_id": None,
            "organization_name": None,
            "path": f"Public documents / {collection.name} / {document.title}",
            "title": document.title, "excerpt": (item.get("excerpt") or "")[:420],
            "page_number": item.get("page"), "score": item["score"],
            "is_archived": False, "collection_id": str(collection.id),
            "source_url": document.source_url, "publisher": document.publisher,
        })
    library_results.sort(key=lambda item: item["score"], reverse=True)
    return file_results[:30], library_results[:20]


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def _search_chats(db: Session, user: User, query: str, folder_id: UUID | None, query_vector: list[float]):
    folders = list_knowledge_bases(db, user.id)
    folder_map = {folder.id: folder for folder in folders}
    allowed_folder_ids = list(folder_map)
    if folder_id:
        allowed_folder_ids = [folder_id] if folder_id in folder_map else []
    visible_shared = and_(
        Conversation.visibility == "shared",
        Conversation.knowledge_base_id.in_(allowed_folder_ids or [UUID(int=0)]),
    )
    access_filter = or_(Conversation.user_id == user.id, visible_shared)
    base = select(Conversation.id).where(access_filter)
    candidate_filter = access_filter
    if folder_id:
        base = base.where(Conversation.knowledge_base_id == folder_id)
        candidate_filter = and_(access_filter, Conversation.knowledge_base_id == folder_id)

    recent_ids = db.scalars(base.order_by(Conversation.created_at.desc()).limit(300)).all()
    text_query = _search_text_query(query)
    searchable_text = func.to_tsvector(literal_column("'simple'"), Conversation.title + " " + Message.content)
    keyword_rows = db.execute(
        select(Conversation.id, func.max(func.ts_rank_cd(searchable_text, text_query)).label("rank"))
        .join(Message, Message.conversation_id == Conversation.id)
        .where(candidate_filter, searchable_text.op("@@")(text_query))
        .group_by(Conversation.id)
        .order_by(func.max(func.ts_rank_cd(searchable_text, text_query)).desc())
        .limit(250)
    ).all()
    candidate_ids = list(dict.fromkeys([row[0] for row in keyword_rows] + list(recent_ids)))[:500]
    if not candidate_ids:
        return []
    conv_rows = db.execute(
        select(Conversation, KnowledgeBase.name, Organization.id, Organization.name, Document.original_filename, LibraryCollection.name)
        .outerjoin(KnowledgeBase, KnowledgeBase.id == Conversation.knowledge_base_id)
        .outerjoin(Organization, Organization.id == KnowledgeBase.organization_id)
        .outerjoin(Document, Document.id == Conversation.document_id)
        .outerjoin(LibraryCollection, LibraryCollection.id == Conversation.library_collection_id)
        .where(Conversation.id.in_(candidate_ids), access_filter)
    ).all()
    recent_messages = (
        select(
            Message.conversation_id.label("conversation_id"),
            Message.role.label("role"),
            Message.content.label("content"),
            Message.created_at.label("created_at"),
            func.row_number().over(
                partition_by=Message.conversation_id,
                order_by=Message.created_at.desc(),
            ).label("message_rank"),
        )
        .where(Message.conversation_id.in_(candidate_ids))
        .subquery()
    )
    messages = db.execute(
        select(recent_messages.c.conversation_id, recent_messages.c.role,
               recent_messages.c.content, recent_messages.c.created_at)
        .where(recent_messages.c.message_rank <= 12)
        .order_by(recent_messages.c.created_at.desc())
    ).all()
    message_text = {}
    first_match = {}
    for conversation_id, role, content, created_at in messages:
        if role == "user" and conversation_id not in first_match:
            first_match[conversation_id] = content[:500]
        existing = message_text.get(conversation_id, "")
        if len(existing) < 3000:
            message_text[conversation_id] = (existing + " " + content[:800])[:3000]
    candidates, embeddings_input = [], []
    for conversation, folder_name, organization_id, organization_name, document_name, collection_name in conv_rows:
        folder = folder_map.get(conversation.knowledge_base_id)
        path = " / ".join(part for part in (
            organization_name or ("Personal folders" if folder_name else "Public documents"),
            folder_name,
            document_name,
            collection_name if not folder_name else None,
            conversation.title,
        ) if part)
        searchable = f"{conversation.title}. {message_text.get(conversation.id, '')}"[:900]
        candidates.append((conversation, folder, organization_id, organization_name, document_name, collection_name, path, searchable))
        embeddings_input.append(searchable)
    vectors = embed_texts(embeddings_input)
    ranks = {row[0]: rank for rank, row in enumerate(keyword_rows, 1)}
    results = []
    for candidate, vector in zip(candidates, vectors):
        conversation, folder, organization_id, organization_name, document_name, collection_name, path, searchable = candidate
        similarity = _cosine(query_vector, vector)
        lexical_rank = ranks.get(conversation.id)
        # Keep exact phrase matches strong while still allowing descriptions
        # with different wording to match by meaning.
        score = similarity + (0.12 / (1 + (lexical_rank or 10_000) / 8)) if lexical_rank else similarity
        if similarity < 0.22 and lexical_rank is None:
            continue
        results.append({
            "id": str(conversation.id), "title": conversation.title,
            "folder_id": str(conversation.knowledge_base_id) if conversation.knowledge_base_id else None,
            "folder_name": folder.name if folder else None,
            "organization_id": str(organization_id) if organization_id else None,
            "organization_name": organization_name, "document_id": str(conversation.document_id) if conversation.document_id else None,
            "document_name": document_name,
            "library_collection_id": str(conversation.library_collection_id) if conversation.library_collection_id else None,
            "library_collection_name": collection_name,
            "scope_type": conversation.scope_type, "visibility": conversation.visibility,
            "path": path, "excerpt": first_match.get(conversation.id, searchable)[:420],
            "created_at": conversation.created_at.isoformat(), "is_archived": conversation.is_archived,
            "score": score,
        })
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:30]


@router.post("/discovery/search")
def search_everything(data: SearchRequest, user: User = Depends(subscribed_user), db: Session = Depends(get_db)):
    """Find authorized files and old chats using text and meaning."""
    query = data.query.strip()
    if len(query) < 2:
        return {"files": [], "public_documents": [], "chats": []}
    enforce_rate_limit(db, "discovery-user", str(user.id), 30, 60)
    query_vector = embed_texts([_meaning_search_text(query)])[0]
    files, public_documents = ([], [])
    if data.kind in {"all", "files"}:
        files, public_documents = _search_files(db, user, query, data.folder_id, query_vector)
    chats = _search_chats(db, user, query, data.folder_id, query_vector) if data.kind in {"all", "chats"} else []
    return {"files": files, "public_documents": public_documents, "chats": chats}


@router.post("/help/ask")
async def ask_how_to_use_documind(data: HelpRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Answer app-use questions using the user guide as the only source."""
    enforce_rate_limit(db, "app-help-user", str(user.id), 20, 60)
    language = requested_language(data.question, user.answer_language or "auto")
    answer, _ = await trusted_answer(
        data.question, GUIDE_CONTEXT, GUIDE_PASSAGES, language=language,
        strict_grounding=True,
    )
    return {
        "answer": answer,
        "sources": [Source(filename="DocuMind user guide", excerpt="Step-by-step help for folders, teams, files, chats, public documents, tools, and privacy.")],
        "answer_language": language,
    }

"""Connect all API endpoint groups under the versioned API prefix."""

from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, knowledge_bases, documents, chat, admin, billing, events, library, organizations, whatsapp, privacy
api_router = APIRouter()
for module in (health, auth, knowledge_bases, documents, chat, admin, billing, events, library, library.admin_router, organizations, whatsapp, privacy):
    api_router.include_router(module.router)

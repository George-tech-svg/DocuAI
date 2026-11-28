"""Connect all API endpoint groups under the versioned API prefix."""

from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, knowledge_bases, documents, chat, admin, billing, events, library, organizations, whatsapp, privacy, business_tools
api_router = APIRouter()
for module in (health, auth, knowledge_bases, documents, chat, admin, billing, events, library, library.admin_router, organizations, whatsapp, privacy, business_tools, business_tools.admin_router):
    api_router.include_router(module.router)

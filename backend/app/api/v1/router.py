"""Connect all API endpoint groups under the versioned API prefix."""

from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, knowledge_bases, documents, chat, admin, billing, events, library, organizations, whatsapp, privacy, business_tools, discovery
api_router = APIRouter()
for module in (health, auth, knowledge_bases, documents, chat, admin, billing, events, library, organizations, whatsapp, privacy, business_tools, discovery):
    api_router.include_router(module.router)

# These are already APIRouter instances, rather than endpoint modules.
api_router.include_router(library.admin_router)
api_router.include_router(business_tools.admin_router)

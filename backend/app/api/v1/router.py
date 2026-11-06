"""Connect all API endpoint groups under the versioned API prefix."""

from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, knowledge_bases, documents, chat
api_router = APIRouter()
for module in (health, auth, knowledge_bases, documents, chat):
    api_router.include_router(module.router)

"""Create the FastAPI application and configure middleware and routing."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.v1.router import api_router
api = FastAPI(title='DocuMind AI', description='Intelligent document management, semantic search, and retrieval-augmented generation', version='1.0.0')
settings = get_settings()
allowed_origins = {
    origin.strip().rstrip('/')
    for origin in (settings.FRONTEND_ORIGIN, *settings.FRONTEND_ORIGINS.split(','))
    if origin.strip()
}
# Keep the production Vercel origin available even when Render's environment
# variable is missing or stale. Additional preview origins remain configurable.
allowed_origins.add('https://docu-ai-sage.vercel.app')
api.include_router(api_router, prefix=get_settings().API_V1_PREFIX)

@api.get('/')
def home():
    return {'app': 'DocuMind AI', 'docs': '/docs'}

# Wrap the complete FastAPI app so CORS headers are also added to unhandled
# 500 responses. Otherwise browser clients can misreport backend crashes as
# a CORS failure because ServerErrorMiddleware sits outside app middleware.
app = CORSMiddleware(
    app=api,
    allow_origins=sorted(allowed_origins),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

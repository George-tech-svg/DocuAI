"""Create the FastAPI application and configure middleware and routing."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.v1.router import api_router
app = FastAPI(title='DocuMind AI', description='Intelligent document management, semantic search, and retrieval-augmented generation', version='1.0.0')
settings = get_settings()
allowed_origins = {
    origin.strip().rstrip('/')
    for origin in (settings.FRONTEND_ORIGIN, *settings.FRONTEND_ORIGINS.split(','))
    if origin.strip()
}
# Keep the production Vercel origin available even when Render's environment
# variable is missing or stale. Additional preview origins remain configurable.
allowed_origins.add('https://docu-ai-sage.vercel.app')
app.add_middleware(CORSMiddleware, allow_origins=sorted(allowed_origins), allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(api_router, prefix=get_settings().API_V1_PREFIX)

@app.get('/')
def home():
    return {'app': 'DocuMind AI', 'docs': '/docs'}

"""Create the FastAPI application and configure middleware and routing."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.v1.router import api_router
app = FastAPI(title='DocuMind AI', description='Intelligent document management, semantic search, and retrieval-augmented generation', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().FRONTEND_ORIGIN], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.include_router(api_router, prefix=get_settings().API_V1_PREFIX)

@app.get('/')
def home():
    return {'app': 'DocuMind AI', 'docs': '/docs'}

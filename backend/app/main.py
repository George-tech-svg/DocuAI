"""Create the FastAPI application and configure middleware and routing."""

import hmac
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.api.v1.router import api_router
api = FastAPI(title='DocuMind AI', description='Intelligent document management, semantic search, and retrieval-augmented generation', version='1.0.0')
settings = get_settings()
allowed_origins = {
    origin.strip().rstrip('/')
    for origin in (settings.FRONTEND_ORIGIN, *settings.FRONTEND_ORIGINS.split(','))
    if origin.strip()
}
# Keep the production Vercel origin available even when an environment value
# is missing or stale. Additional preview origins remain configurable.
allowed_origins.add('https://docuai-jet.vercel.app')
api.include_router(api_router, prefix=get_settings().API_V1_PREFIX)

@api.middleware('http')
async def csrf_guard(request: Request, call_next):
    """Double-submit CSRF protection for browser mutations using cookies."""
    if request.method in {'GET', 'HEAD', 'OPTIONS', 'TRACE'}:
        return await call_next(request)
    path = request.url.path
    api_prefix = get_settings().API_V1_PREFIX.rstrip('/')
    mpesa_callback_prefix = f'{api_prefix}/billing/mpesa/callback/'
    whatsapp_webhook_path = f'{api_prefix}/channels/whatsapp/webhook'
    if path.startswith(mpesa_callback_prefix) or path == whatsapp_webhook_path:
        return await call_next(request)
    cookie_value = request.cookies.get('documind_csrf')
    header_value = request.headers.get('X-CSRF-Token')
    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        return JSONResponse({'detail': 'Request verification failed. Refresh the page and try again.'}, status_code=403)
    return await call_next(request)

@api.get('/')
def home():
    return {'app': 'DocuMind AI', 'docs': '/docs'}

# Wrap the complete FastAPI app so CORS headers are also added to unhandled
# 500 responses. Otherwise browser clients can misreport backend crashes as
# a CORS failure because ServerErrorMiddleware sits outside app middleware.
app = CORSMiddleware(
    app=api,
    allow_origins=sorted(allowed_origins),
    # The app uses credentialed cookie sessions. Trust only configured origins;
    # preview deployments must be explicitly listed in FRONTEND_ORIGINS.
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

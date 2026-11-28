"""Persist original documents in Cloudinary."""

import cloudinary
import cloudinary.uploader
from io import BytesIO
from urllib.parse import urlparse
import httpx
from app.core.config import get_settings

def store_file(filename: str, data: bytes):
    """Upload a document and fail explicitly if Cloudinary is not configured."""
    s = get_settings()
    if not (s.CLOUDINARY_CLOUD_NAME and s.CLOUDINARY_API_KEY and s.CLOUDINARY_API_SECRET):
        raise RuntimeError('Cloudinary storage is not configured')
    cloudinary.config(cloud_name=s.CLOUDINARY_CLOUD_NAME, api_key=s.CLOUDINARY_API_KEY, api_secret=s.CLOUDINARY_API_SECRET, secure=True)
    # Cloudinary requires chunked uploads above 100 MB. Use a file-like source
    # so its SDK can send bounded chunks instead of one oversized HTTP request.
    source = BytesIO(data)
    # Bound each network request so a stalled Cloudinary connection cannot
    # leave the upload in processing indefinitely. Large uploads use 20 MB
    # chunks, each with its own request timeout.
    options = {'resource_type': 'raw', 'folder': 'documind', 'use_filename': False, 'unique_filename': True, 'timeout': 120}
    if len(data) > 100 * 1024 * 1024:
        result = cloudinary.uploader.upload_large(source, chunk_size=20 * 1024 * 1024, **options)
    else:
        result = cloudinary.uploader.upload(source, **options)
    return {'public_id': result['public_id'], 'resource_type': result['resource_type'], 'url': result['secure_url']}

def delete_file(public_id: str, resource_type: str = 'raw', asset_type: str = 'upload'):
    """Delete a previously stored original from Cloudinary."""
    s = get_settings()
    if not (s.CLOUDINARY_CLOUD_NAME and s.CLOUDINARY_API_KEY and s.CLOUDINARY_API_SECRET):
        raise RuntimeError('Cloudinary storage is not configured')
    cloudinary.config(cloud_name=s.CLOUDINARY_CLOUD_NAME, api_key=s.CLOUDINARY_API_KEY, api_secret=s.CLOUDINARY_API_SECRET, secure=True)
    result = cloudinary.uploader.destroy(public_id, resource_type=resource_type, type=asset_type, invalidate=True, timeout=30)
    if result.get('result') not in {'ok', 'not found'}:
        raise RuntimeError('Cloudinary could not delete the stored document')

def store_export_file(path: str, public_id: str):
    """Store a privacy archive as an authenticated Cloudinary raw asset."""
    s = get_settings()
    if not (s.CLOUDINARY_CLOUD_NAME and s.CLOUDINARY_API_KEY and s.CLOUDINARY_API_SECRET):
        raise RuntimeError('Cloudinary storage is not configured')
    cloudinary.config(cloud_name=s.CLOUDINARY_CLOUD_NAME, api_key=s.CLOUDINARY_API_KEY,
        api_secret=s.CLOUDINARY_API_SECRET, secure=True)
    result = cloudinary.uploader.upload(path, resource_type='raw', type='authenticated',
        folder='documind/privacy-exports', public_id=public_id, use_filename=False,
        unique_filename=False, timeout=120)
    return {'public_id':result['public_id'],'resource_type':result['resource_type']}

def private_export_url(public_id: str) -> str:
    """Return a short-lived signed download URL for a private export archive."""
    import time
    import cloudinary.utils
    s = get_settings()
    cloudinary.config(cloud_name=s.CLOUDINARY_CLOUD_NAME, api_key=s.CLOUDINARY_API_KEY,
        api_secret=s.CLOUDINARY_API_SECRET, secure=True)
    return cloudinary.utils.private_download_url(public_id, 'zip', resource_type='raw',
        type='authenticated', attachment=True, expires_at=int(time.time()) + 300)

def download_file(url: str, max_bytes: int) -> bytes:
    """Fetch a previously stored Cloudinary original with strict host/size limits."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not (parsed.hostname == 'res.cloudinary.com' or (parsed.hostname or '').endswith('.res.cloudinary.com')):
        raise RuntimeError('The stored original file could not be retrieved. Please upload the file again.')
    parts = []
    total = 0
    try:
        with httpx.stream('GET', url, timeout=httpx.Timeout(30, connect=10), follow_redirects=False) as response:
            response.raise_for_status()
            for part in response.iter_bytes():
                total += len(part)
                if total > max_bytes:
                    raise RuntimeError('The stored original file is larger than the configured upload limit.')
                parts.append(part)
    except httpx.HTTPError as exc:
        raise RuntimeError('The stored original file could not be retrieved. Please try uploading it again.') from exc
    return b''.join(parts)

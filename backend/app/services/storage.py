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

def delete_file(public_id: str, resource_type: str = 'raw'):
    """Delete a previously stored original from Cloudinary."""
    s = get_settings()
    if not (s.CLOUDINARY_CLOUD_NAME and s.CLOUDINARY_API_KEY and s.CLOUDINARY_API_SECRET):
        raise RuntimeError('Cloudinary storage is not configured')
    cloudinary.config(cloud_name=s.CLOUDINARY_CLOUD_NAME, api_key=s.CLOUDINARY_API_KEY, api_secret=s.CLOUDINARY_API_SECRET, secure=True)
    result = cloudinary.uploader.destroy(public_id, resource_type=resource_type, invalidate=True, timeout=30)
    if result.get('result') not in {'ok', 'not found'}:
        raise RuntimeError('Cloudinary could not delete the stored document')

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

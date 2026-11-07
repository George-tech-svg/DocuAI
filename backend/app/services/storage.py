"""Persist original documents in Cloudinary."""

import cloudinary
import cloudinary.uploader
from io import BytesIO
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
    options = {'resource_type': 'raw', 'folder': 'documind', 'use_filename': False, 'unique_filename': True}
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
    result = cloudinary.uploader.destroy(public_id, resource_type=resource_type, invalidate=True)
    if result.get('result') not in {'ok', 'not found'}:
        raise RuntimeError('Cloudinary could not delete the stored document')

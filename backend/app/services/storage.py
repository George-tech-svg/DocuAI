"""Optionally upload original documents to Cloudinary."""

import cloudinary
import cloudinary.uploader
from app.core.config import get_settings

def store_file(filename: str, data: bytes):
    """Upload a copy to Cloudinary when storage credentials are configured."""
    s = get_settings()
    if not (s.CLOUDINARY_CLOUD_NAME and s.CLOUDINARY_API_KEY and s.CLOUDINARY_API_SECRET):
        return None
    cloudinary.config(cloud_name=s.CLOUDINARY_CLOUD_NAME, api_key=s.CLOUDINARY_API_KEY, api_secret=s.CLOUDINARY_API_SECRET, secure=True)
    result = cloudinary.uploader.upload(data, resource_type='raw', folder='documind', use_filename=False, unique_filename=True)
    return {'public_id': result['public_id'], 'resource_type': result['resource_type'], 'url': result['secure_url']}

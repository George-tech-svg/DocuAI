"""Ingest the official document entries in a YAML manifest.

Run from backend environment: python scripts/ingest_library.py --manifest docs/kenyan_library_manifest.example.yaml
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from datetime import date, datetime, time, timezone
import yaml
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.db.session import get_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from app.models.entities import LibraryCollection, LibraryDocument  # noqa: E402
from app.services.library_ingestion import ingest_library_document, validate_official_source_url  # noqa: E402

ALLOWED_CATEGORIES = {'tax', 'employment', 'procurement', 'companies', 'data-protection', 'education', 'courts'}

def parse_date(value):
    if value in (None, ''): return None
    if isinstance(value, datetime): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date): return datetime.combine(value, time.min, tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

def main():
    parser = argparse.ArgumentParser(description='Download and index direct official document URLs from a YAML manifest.')
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    manifest = yaml.safe_load(args.manifest.read_text(encoding='utf-8')) or {}
    if not isinstance(manifest, dict) or not isinstance(manifest.get('collections'), list):
        parser.error('Manifest must contain a collections list.')
    with sessionmaker(bind=get_engine())() as db:
        for item in manifest['collections']:
            category = item.get('category')
            if category not in ALLOWED_CATEGORIES: raise ValueError(f'Unsupported collection category: {category}')
            slug = item['slug']
            collection = db.scalar(select(LibraryCollection).where(LibraryCollection.slug == slug))
            if not collection:
                collection = LibraryCollection(slug=slug, name=item['name'], description=item.get('description', ''), category=category)
                db.add(collection); db.flush()
            else:
                collection.name=item['name']; collection.description=item.get('description', ''); collection.category=category
            for source in item.get('documents', []):
                url = validate_official_source_url(source['source_url'])
                existing = db.scalar(select(LibraryDocument).where(LibraryDocument.collection_id == collection.id, LibraryDocument.short_name == source['short_name'], LibraryDocument.version_label == source['version_label'], LibraryDocument.status.in_(['queued', 'processing'])).limit(1))
                if existing:
                    print(f"Already queued: {source['title']}")
                    continue
                doc = LibraryDocument(collection_id=collection.id, title=source['title'], short_name=source['short_name'], source_url=url, publisher=source['publisher'], version_label=source['version_label'], document_date=parse_date(source.get('document_date')), effective_from=parse_date(source.get('effective_from')), status='queued', is_current=False)
                db.add(doc); db.commit(); db.refresh(doc)
                try:
                    result = ingest_library_document(db, doc.id)
                    print(f"{source['title']}: {result['status']}")
                except Exception as exc:
                    print(f"{source['title']}: FAILED - {exc}", file=sys.stderr)
        db.commit()

if __name__ == '__main__': main()

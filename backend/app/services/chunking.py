"""Split document pages into smaller passages for semantic search."""

import re

def chunk_pages(pages: list[tuple[int, str]], size: int=1100, overlap: int=180):
    """Split extracted pages into passages suitable for embeddings."""
    output = []
    for page, text in pages:
        cleaned = re.sub('\\s+', ' ', text).strip()
        pos = 0
        while pos < len(cleaned):
            part = cleaned[pos:pos + size].strip()
            if part:
                output.append((page, part))
            if pos + size >= len(cleaned):
                break
            pos += size - overlap
    return output

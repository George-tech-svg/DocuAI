"""Convert text passages into 384-dimensional MiniLM vectors."""

from functools import lru_cache
from sentence_transformers import SentenceTransformer

@lru_cache(maxsize=1)
def model():
    return SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

def embed_texts(texts: list[str]):
    """Generate semantic vectors for the supplied text passages."""
    if not texts:
        return []
    vectors = model().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]

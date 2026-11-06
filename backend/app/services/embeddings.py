"""Convert text passages into 384-dimensional MiniLM vectors."""

from functools import lru_cache

@lru_cache(maxsize=1)
def model():
    # Load the ML runtime only when an upload or chat actually needs an
    # embedding. This keeps the API and health check responsive at startup.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu')

def embed_texts(texts: list[str]):
    """Generate semantic vectors for the supplied text passages."""
    if not texts:
        return []
    vectors = model().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]

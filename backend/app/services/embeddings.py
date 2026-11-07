"""Convert text passages into 384-dimensional MiniLM vectors."""

from functools import lru_cache
import logging
from pathlib import Path
from time import perf_counter

logger = logging.getLogger(__name__)
MODEL_ID = 'sentence-transformers/all-MiniLM-L6-v2'
MODEL_CACHE_DIR = Path(__file__).resolve().parents[2] / '.model-cache'

@lru_cache(maxsize=1)
def model():
    # Load the ML runtime only when an upload or chat actually needs an
    # embedding. This keeps the API and health check responsive at startup.
    started = perf_counter()
    logger.warning('Loading the sentence embedding model.')
    from sentence_transformers import SentenceTransformer

    instance = SentenceTransformer(
        MODEL_ID,
        device='cpu',
        cache_folder=str(MODEL_CACHE_DIR),
    )
    logger.warning('Sentence embedding model loaded in %.1f seconds.', perf_counter() - started)
    return instance

def embed_texts(texts: list[str]):
    """Generate semantic vectors for the supplied text passages."""
    if not texts:
        return []
    started = perf_counter()
    vectors = model().encode(texts, normalize_embeddings=True)
    elapsed = perf_counter() - started
    if elapsed >= 3:
        logger.warning('Encoded %s text(s) in %.1f seconds.', len(texts), elapsed)
    return [v.tolist() for v in vectors]

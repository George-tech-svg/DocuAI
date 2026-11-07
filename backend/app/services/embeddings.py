"""Convert text passages into 384-dimensional MiniLM vectors."""

import logging
from pathlib import Path
from threading import Lock
from time import perf_counter

logger = logging.getLogger(__name__)
MODEL_ID = 'sentence-transformers/all-MiniLM-L6-v2'
MODEL_CACHE_DIR = Path(__file__).resolve().parents[2] / '.model-cache'
_model_instance = None
_model_lock = Lock()

def model():
    # Load the ML runtime only when an upload or chat actually needs an
    # embedding. This keeps the API and health check responsive at startup.
    global _model_instance
    if _model_instance is not None:
        return _model_instance

    # functools.lru_cache can execute the wrapped function more than once when
    # concurrent requests arrive during the first cache miss. Keep one model
    # load in flight so simultaneous requests do not duplicate its RAM use.
    with _model_lock:
        if _model_instance is None:
            started = perf_counter()
            logger.warning('Loading the sentence embedding model.')
            from sentence_transformers import SentenceTransformer

            _model_instance = SentenceTransformer(
                MODEL_ID,
                device='cpu',
                cache_folder=str(MODEL_CACHE_DIR),
            )
            logger.warning('Sentence embedding model loaded in %.1f seconds.', perf_counter() - started)
    return _model_instance

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

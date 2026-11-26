"""Convert text passages into 384-dimensional MiniLM vectors."""

import logging
import os
from pathlib import Path
from threading import Lock
from time import perf_counter

logger = logging.getLogger(__name__)
MODEL_ID = 'sentence-transformers/all-MiniLM-L6-v2'
# Keep the cache in a visible directory so Vercel's function bundler can include
# its downloaded ONNX files. The build preloader warms this cache before deploy.
MODEL_CACHE_DIR = Path(__file__).resolve().parents[2] / 'model-cache'
_model_instance = None
_model_lock = Lock()
_encode_lock = Lock()

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
            os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
            from fastembed import TextEmbedding

            MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _model_instance = TextEmbedding(
                model_name=MODEL_ID,
                cache_dir=str(MODEL_CACHE_DIR),
                threads=1,
            )
            logger.warning('Sentence embedding model loaded in %.1f seconds.', perf_counter() - started)
    return _model_instance

def iter_embedding_batches(texts: list[str], batch_size: int = 8):
    """Yield small embedding batches to keep peak CPU memory bounded."""
    if not texts:
        return
    for offset in range(0, len(texts), batch_size):
        batch = texts[offset:offset + batch_size]
        started = perf_counter()
        # Serialize inference. Multiple uploads or chats must not each allocate
        # a separate set of model activations at the same time on a small host.
        with _encode_lock:
            vectors = list(model().embed(
                batch,
                batch_size=batch_size,
            ))
        elapsed = perf_counter() - started
        if elapsed >= 3:
            logger.warning('Encoded %s text(s) in %.1f seconds.', len(batch), elapsed)
        yield [vector.tolist() for vector in vectors]


def embed_texts(texts: list[str]):
    """Generate semantic vectors for a small request such as a chat query."""
    return [vector for batch in iter_embedding_batches(texts) for vector in batch]

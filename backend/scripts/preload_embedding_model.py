"""Download and validate the FastEmbed model during the service build."""

from pathlib import Path
import sys

# Support both Render layouts: repository root and `backend` as root directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.embeddings import MODEL_CACHE_DIR, MODEL_ID, model


def main():
    print(f"Preloading {MODEL_ID} into {MODEL_CACHE_DIR}", flush=True)
    embedder = model()
    vectors = list(embedder.embed(["Vercel build model validation"], batch_size=1))
    if len(vectors) != 1 or len(vectors[0]) != 384:
        raise RuntimeError("FastEmbed model validation failed: expected one 384-dimensional vector.")
    print("Embedding model download and initialization complete.", flush=True)


if __name__ == "__main__":
    main()

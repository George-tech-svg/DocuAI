"""Download the embedding model during the Render build, not a user request."""

from pathlib import Path
import sys

from huggingface_hub import snapshot_download

# Support both Render layouts: repository root and `backend` as root directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.embeddings import MODEL_CACHE_DIR, MODEL_ID


def main():
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Preloading {MODEL_ID} into {MODEL_CACHE_DIR}", flush=True)
    snapshot_download(repo_id=MODEL_ID, cache_dir=str(MODEL_CACHE_DIR))
    print("Embedding model download complete.", flush=True)


if __name__ == "__main__":
    main()

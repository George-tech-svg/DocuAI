# DocuMind AI — Full-Stack Document Q&A System

DocuMind AI lets users register, create private knowledge bases, upload documents, and ask AI questions about them.

For the complete current feature, architecture, API, database, deployment, and environment guide, see [docs/SYSTEM_DOCUMENTATION.md](docs/SYSTEM_DOCUMENTATION.md).

See [PRODUCT_VISION_KENYA.md](PRODUCT_VISION_KENYA.md) for the education-first product direction, validation plan, safeguards, and future improvements.

## Project layout

- `backend/app/api/` — FastAPI routes and login protection.
- `backend/app/models/` — SQLAlchemy database tables.
- `backend/app/schemas/` — Pydantic input and output validation.
- `backend/app/services/` — Document processing, embeddings, retrieval, and AI logic.
- `backend/worker.py` — Long-lived PostgreSQL queue worker for indexing and OCR.
- `render.yaml` — Render Background Worker deployment definition.
- `backend/sql/` — Schema reference for a **new, empty database only**.
- `backend/tests/` — Small unit tests.
- `frontend/src/` — React user interface and API client.

## Before running

Keep `.env` files and credentials private. The backend reads the existing `frontend/.env` and optionally `backend/.env` (which takes precedence). The SQL file is reference material for a new empty database; do not run it against an existing Neon database.

## Backend (PowerShell)

```powershell
Set-Location 'PATH_TO_EXTRACTED_PROJECT\DocuMind_AI\backend'
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Review `backend/ENV_SETUP.md` to confirm the local credential names. Then run:

```powershell
python -m uvicorn app.main:app --reload
```

For local document processing, also install `requirements-worker.txt`, install Tesseract with `eng` and `swa` language data and libheif, apply the database migrations, then run `python worker.py` from `backend/` in a third terminal. Without the worker, accepted uploads remain queued.

## Create or update the Neon schema

After installing the backend requirements and configuring `DATABASE_URL` for Neon, run `npm run migrate` from the repository root or from `frontend/`. This applies the versioned Alembic migrations, creates missing tables, and safely adds compatible missing columns. It does not drop tables or rows. If a required new column needs real values for existing rows, the migration stops and identifies the column so it can be backfilled before rerunning.

The old `backend/sql/001_schema.sql` is kept as a reference for a new empty database; use the migration command for normal setup and schema changes.

Swagger: http://127.0.0.1:8000/docs

## Frontend (second terminal)

```powershell
Set-Location 'PATH_TO_EXTRACTED_PROJECT\DocuMind_AI\frontend'
npm install
npm run dev
```

Frontend: http://localhost:3000

## How document Q&A works

1. User logs in and creates a knowledge base.
2. User uploads a PDF, TXT, DOCX, JPG, PNG, or HEIC file (10 MB per file by default; configurable with `MAX_UPLOAD_MB`). Multiple JPG/PNG photos can be combined into one PDF from the upload picker.
3. The API stores the original in Cloudinary, creates a pending record, queues an indexing job in PostgreSQL, and returns HTTP 202.
4. The Render Background Worker claims the job with `FOR UPDATE SKIP LOCKED`, extracts text, OCRs sparse PDF pages/photos using Tesseract (`eng+swa`), and reports progress stages.
5. FastEmbed runs the MiniLM ONNX model to generate 384-dimensional embeddings; PostgreSQL pgvector stores them.
6. A question is embedded and vector similarity plus PostgreSQL full-text keyword search find candidates within the selected document or folder. Reciprocal-rank fusion selects up to five passages for DeepSeek, which answers with document/page sources.

## Important limitations

- Vercel deploys the frontend and FastAPI backend as services from the repository root.
- The Render worker requires Tesseract with English and Swahili data, libheif, and the dependencies in `backend/requirements-worker.txt`. Configure it with the same `DATABASE_URL` and `MAX_UPLOAD_MB` as Vercel, then apply migration `0013`.
- OCR can misread low-quality pages; the UI warns when OCR confidence is low. The worker records errors, retries with exponential backoff, and exposes terminal failures in the admin Jobs area.
- Original files are stored in Cloudinary, while document metadata, extracted text, embeddings, accounts, and conversations are stored in Neon. Uploads fail if Cloudinary storage is not configured. Deleting a document or knowledge base also removes the associated Cloudinary originals.
- In Vercel, set the project framework to **Services** and configure the backend variables listed in `backend/ENV_SETUP.md`. FastEmbed's ONNX runtime replaces PyTorch to keep the backend function bundle under the standard size limit.
- The default file cap is 10 MB per file and is configurable up to the 50 MB service ceiling; the hosting platform may impose a lower request-body limit. The frontend uses same-origin `/api/v1`; set `VITE_API_BASE_URL` only if the backend is deployed as a separate project.
- Review the schema and ownership/deletion behavior before migrating an existing database.

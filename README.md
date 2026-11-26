# DocuMind AI — Full-Stack Document Q&A System

DocuMind AI lets users register, create private knowledge bases, upload documents, and ask AI questions about them.

## Project layout

- `backend/app/api/` — FastAPI routes and login protection.
- `backend/app/models/` — SQLAlchemy database tables.
- `backend/app/schemas/` — Pydantic input and output validation.
- `backend/app/services/` — Document processing, embeddings, retrieval, and AI logic.
- `backend/sql/` — Schema reference for a **new, empty database only**.
- `backend/tests/` — Small unit tests.
- `frontend/src/` — React user interface and API client.

## Before running

Keep `.env` files and credentials private. The backend reads the existing `frontend/.env` and optionally `backend/.env` (which takes precedence). The SQL file is reference material for a new empty database; do not run it against an existing Neon database.

## Backend (PowerShell)

```powershell
Set-Location 'PATH_TO_EXTRACTED_PROJECT\DocuMind_AI\backend'
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Review `backend/ENV_SETUP.md` to confirm the local credential names. Then run:

```powershell
python -m uvicorn app.main:app --reload
```

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
2. User uploads a PDF, DOCX, or TXT file (up to 20 MB; indexing continues in the background).
3. Backend extracts text and splits it into chunks.
4. FastEmbed runs the MiniLM ONNX model to generate 384-dimensional embeddings; PostgreSQL pgvector stores them.
5. A question is embedded and similar chunks are retrieved.
6. DeepSeek receives retrieved excerpts and produces an answer with sources.

## Important limitations

- Vercel deploys the frontend and FastAPI backend as services from the repository root.
- The local PostgreSQL connection and pgvector extension were checked read-only, the frontend production build succeeds, and backend unit tests pass.
- PDF extraction handles text PDFs; scanned PDFs require OCR, which is not included.
- On Vercel, uploads are indexed before the API request returns so serverless instance recycling cannot abandon work. Persistent hosts use a serialized in-process background task; use a durable queue and separate worker for restart-safe processing there.
- Original files are stored in Cloudinary, while document metadata, extracted text, embeddings, accounts, and conversations are stored in Neon. Uploads fail if Cloudinary storage is not configured. Deleting a document or knowledge base also removes the associated Cloudinary originals.
- In Vercel, set the project framework to **Services** and configure the backend variables listed in `backend/ENV_SETUP.md`. FastEmbed's ONNX runtime replaces PyTorch to keep the backend function bundle under the standard size limit.
- The app accepts files up to 20 MB. Vercel's 20 MiB request body beta requires `VERCEL_SUPPORT_LARGE_REQUEST_BODY=1` and 4 GB Performance memory on the backend service, which Hobby projects cannot select. On Hobby, use direct-to-Cloudinary uploads or keep the request body under Vercel's standard 4.5 MB limit. The frontend uses same-origin `/api/v1`; set `VITE_API_BASE_URL` only if the backend is deployed as a separate project.
- Review the schema and ownership/deletion behavior before migrating an existing database.

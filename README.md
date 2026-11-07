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
2. User uploads a PDF, DOCX, or TXT file (5 GB application limit by default; hosting and storage plans may impose lower limits).
3. Backend extracts text and splits it into chunks.
4. MiniLM generates 384-dimensional embeddings; PostgreSQL pgvector stores them.
5. A question is embedded and similar chunks are retrieved.
6. DeepSeek receives retrieved excerpts and produces an answer with sources.

## Important limitations

- This repository contains the local application source; it is not yet a published deployment.
- The local PostgreSQL connection and pgvector extension were checked read-only, the frontend production build succeeds, and backend unit tests pass.
- PDF extraction handles text PDFs; scanned PDFs require OCR, which is not included.
- File processing currently runs during the upload request; for larger deployments, use a background job queue.
- Original files are stored in Cloudinary, while document metadata, extracted text, embeddings, accounts, and conversations are stored in Neon. Uploads fail if Cloudinary storage is not configured. Deleting a document or knowledge base also removes the associated Cloudinary originals.
- For deployment, set `VITE_API_BASE_URL` in Vercel to the deployed FastAPI URL ending in `/api/v1`. Set `FRONTEND_URL` on the backend to the deployed Vercel origin. Local `.env` values do not configure production deployments.
- Review the schema and ownership/deletion behavior before migrating an existing database.

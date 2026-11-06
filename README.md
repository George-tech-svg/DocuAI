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
2. User uploads a PDF, DOCX, or TXT file (10 MB limit by default).
3. Backend extracts text and splits it into chunks.
4. MiniLM generates 384-dimensional embeddings; PostgreSQL pgvector stores them.
5. A question is embedded and similar chunks are retrieved.
6. DeepSeek receives retrieved excerpts and produces an answer with sources.

## Important limitations

- This repository contains the local application source; it is not yet a published deployment.
- The local PostgreSQL connection and pgvector extension were checked read-only, the frontend production build succeeds, and backend unit tests pass.
- PDF extraction handles text PDFs; scanned PDFs require OCR, which is not included.
- File processing currently runs during the upload request; for larger deployments, use a background job queue.
- Original file storage in Cloudinary is optional. Without Cloudinary credentials, document text and embeddings are still stored in the database, but the original upload is not retained.
- Review the schema and ownership/deletion behavior before migrating an existing database.

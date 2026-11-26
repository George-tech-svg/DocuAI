# Environment setup

## Vercel deployment

This repository deploys the Vite frontend and FastAPI backend as two services
in one Vercel project. The frontend calls `/api/v1` on the same domain, and
`vercel.json` routes `/api/*` to the backend. Leave `VITE_API_BASE_URL` unset
for this setup.

The repository-root `.env.vercel` file is prepared from the current
`backend/.env`. It retains the existing Neon, JWT, DeepSeek, and Cloudinary
credentials, updates the frontend origins to `https://docuai-jet.vercel.app`,
and sets the 5-million-character extraction limit. It is gitignored because it
contains secrets. Import it in Vercel's Project Settings → Environment
Variables, choose Production and Preview as needed, and redeploy. Do not share
the file or commit it. Keep secrets assigned to the backend service. Vercel
system variables such as `VERCEL` are provided by Vercel; do not add
`VERCEL_SUPPORT_*` keys manually if the dashboard marks them invalid.

Required backend variables:

- `DATABASE_URL`: Neon PostgreSQL connection string.
- `JWT_SECRET_KEY`: signing secret used by the application.
- `DEEPSEEK_API_KEY`: DeepSeek key for chat.
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`:
  Cloudinary credentials used to store uploaded originals.
- `FRONTEND_ORIGIN` and `FRONTEND_URL`: production site origin, with no
  trailing slash. The prepared file uses `https://docuai-jet.vercel.app`.
- `FRONTEND_ORIGINS`: optional comma-separated extra origins.
- `MAX_UPLOAD_MB`: application-level limit, capped by the app at 20 MB.
- `MAX_EXTRACTED_CHARS`: extracted text limit, capped at 5,000,000.
- `DEEPSEEK_MODEL`: optional; defaults to `deepseek-flash`.
- `API_V1_PREFIX`: defaults to `/api/v1`.

`APP_ENV`, `APP_NAME`, `APP_VERSION`, and `DEBUG` are retained from the
existing environment file for continuity; the API currently uses its own
application metadata defaults. No frontend API URL is needed for the shared
domain.

The backend build preloads FastEmbed's ONNX model into `backend/model-cache`
and validates that it can produce a 384-dimensional vector. The cache is inside
the backend service root, where Vercel's Python runtime packages project files
reachable at build time. If model preloading fails, the deployment build should
fail with the underlying download or model error. The Vercel Services schema
does not accept `includeFiles` inside a service definition, so it is not set in
`vercel.json`.

Vercel's normal function request body limit is 4.5 MB. Its optional 20 MiB
request-body beta requires eligible plan settings, Fluid Compute, and 4 GB
Performance memory. An application-side `MAX_UPLOAD_MB=20` setting cannot
raise Vercel's proxy limit by itself. Files above Vercel's active body limit
need a direct-to-Cloudinary upload flow.

## Local development

The backend reads `frontend/.env` and then `backend/.env`; shell environment
variables take precedence. Install `backend/requirements.txt`, then run the
FastAPI app from the backend directory. For Vite development, set
`VITE_DEV_API_PROXY_TARGET` to the FastAPI origin, or set
`VITE_API_BASE_URL` to the full local API prefix. Never put backend secrets in
`VITE_*` variables.

Apply database migrations with `npm run migrate` from the repository root. Run
this after pulling updates that change the database schema and before using the
new backend. The document-scoped chat history migration adds a nullable link
from each conversation to its document; existing conversations stay available
as folder-level chats.
Local `.env` files do not configure Vercel; update the Vercel project
environment and redeploy after changing production variables.

# Backend environment configuration

The backend reads `frontend/.env` (the credentials file already used by this
project) and then `backend/.env` if present. Values in `backend/.env` take
precedence. Neither file should be committed or included in a shared ZIP.

Required keys:

- `DATABASE_URL`: Complete Neon PostgreSQL connection URL.
- `JWT_SECRET_KEY`: A long, random signing secret.
- `DEEPSEEK_API_KEY`: Your DeepSeek API key for grounded chat answers.

Additional service configuration:

- `DEEPSEEK_MODEL`: Optional; defaults to `deepseek-flash`. The current DeepSeek API model names are `deepseek-flash` and `deepseek-v4-pro`; the legacy `deepseek-chat` name was discontinued.
- `FRONTEND_URL` or `FRONTEND_ORIGIN`: The exact deployed frontend origin, used by backend CORS.
- `FRONTEND_ORIGINS`: Optional comma-separated list of additional exact frontend origins, such as Vercel preview domains.
- `MAX_UPLOAD_SIZE_MB` or `MAX_UPLOAD_MB`: Defaults to `20` MB. The API enforces a 20 MB maximum, even if the environment variable is set higher.
- `MAX_EXTRACTED_CHARS`: Defaults to `5,000,000` characters, with a hard maximum of 5 million to bound extraction and indexing work.
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: Required. An upload is only marked ready after its original is stored in Cloudinary and its text/chunks are saved in Neon.

The Vite frontend reads `VITE_API_BASE_URL` at build time. For this repository's shared Vercel Services deployment, leave it unset; the frontend uses the same-origin `/api/v1` rewrite. If you deploy the backend as a separate project, set it to that backend URL ending in `/api/v1`. Do not use a localhost URL in Vercel. For local development, set `VITE_API_BASE_URL` to your local API URL, or set `VITE_DEV_API_PROXY_TARGET` to the local FastAPI origin when using the relative `/api/v1` default.

Set all service variables in the backend hosting provider as well as the appropriate Vercel variables. Local `.env` files do not configure deployed services.

The backend uses FastEmbed's ONNX runtime rather than PyTorch so its function
bundle stays below Vercel's standard Python size limit. The app accepts files
up to 20 MB, but Vercel's standard request body limit is 4.5 MB. The 20 MiB
request-body beta needs `VERCEL_SUPPORT_LARGE_REQUEST_BODY=1` and Performance
(4 GB) function memory. Hobby projects cannot select 4 GB; on Hobby, use
direct-to-Cloudinary uploads or keep uploads below Vercel's request body limit.

Add the application variables listed above to the backend service environment
in Vercel. For this shared-domain deployment, leave `VITE_API_BASE_URL` unset;
the frontend calls `/api/v1` on the same domain. Set `FRONTEND_ORIGIN` to the
deployed frontend origin if you use a custom domain.

For Render, append the model preload script to the existing build command
after dependency installation. Use the command matching the service's root
directory:

- Root Directory `backend`:
  `pip install -r requirements.txt && python scripts/preload_embedding_model.py`
- Root Directory at the repository root:
  `pip install -r backend/requirements.txt && python backend/scripts/preload_embedding_model.py`

This downloads the MiniLM ONNX embedding model while building the release, so a
user's first upload or chat request does not need to fetch model files from
Hugging Face. The cache is kept in the build artifact and is excluded from Git.
If model preloading fails during the build, inspect that build error; the live
service would otherwise try the same download during a request.

In Render's Environment page, set `DEEPSEEK_API_KEY` to a valid key from the
DeepSeek Platform and set `DEEPSEEK_MODEL` to `deepseek-flash`. Keep the key
only in Render's environment settings; never put it in frontend variables or
source control. The chat endpoint uses the OpenAI-compatible
`https://api.deepseek.com/chat/completions` endpoint with bearer authentication.

Set Render's `FRONTEND_URL` to the production Vercel domain shown under **Project Settings → Domains** (no trailing slash). The backend also accepts HTTPS `*.vercel.app` domains so Vercel's deployment-specific preview hostnames do not block API requests. Add any custom non-Vercel domains to `FRONTEND_ORIGINS` as a comma-separated list, then redeploy the Render service.

Ready-to-import production settings are in `backend/.env.render`; in Render, open the service's **Environment** page and choose **Add from .env**, select that file, then save and deploy. The file is gitignored because it contains credentials copied from the existing local environment. `frontend/.env.vercel` contains only the public API base URL. Vercel's dashboard does not import a `.env` file; add that single `VITE_API_BASE_URL` value under **Project Settings → Environment Variables** for Production (and Preview if needed), then redeploy.

On Vercel, document indexing completes before the upload request returns because serverless instances may be recycled after a response. On persistent hosts, the API accepts the upload immediately and indexes it in a background task; the frontend polls until it becomes `ready` or `failed`. Heavy indexing is serialized within one backend process, uploads remain capped at 20 MB, extracted text at 5 million characters, and embeddings are generated in small batches.

The background task runs in the same Render process as the API, so a process restart can still interrupt indexing. The stale-processing check marks abandoned entries failed after 15 minutes. For production reliability across restarts, use a durable job queue and a separate worker. A larger Render instance may also be needed if the service reaches its memory limit. Preload the embedding model during the Render build using the command above; otherwise the first upload downloads it at runtime and can take several minutes.

Install `backend/requirements.txt`, configure `DATABASE_URL` for Neon, then run `npm run migrate` from the repository root or `frontend/`. The command applies the Alembic migration version table and creates missing application tables and columns without dropping existing data. If a required column cannot be populated safely on existing records, the command stops and names the column rather than filling it with fake data.

Keep all secrets private. The application will not start without the database URL and JWT signing secret.

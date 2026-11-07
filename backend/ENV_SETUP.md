# Backend environment configuration

The backend reads `frontend/.env` (the credentials file already used by this
project) and then `backend/.env` if present. Values in `backend/.env` take
precedence. Neither file should be committed or included in a shared ZIP.

Required keys:

- `DATABASE_URL`: Complete Neon PostgreSQL connection URL.
- `JWT_SECRET_KEY`: A long, random signing secret.
- `DEEPSEEK_API_KEY`: Your DeepSeek API key for grounded chat answers.

Additional service configuration:

- `DEEPSEEK_MODEL`: Optional; defaults to `deepseek-chat`.
- `FRONTEND_URL` or `FRONTEND_ORIGIN`: The exact deployed frontend origin, used by backend CORS.
- `FRONTEND_ORIGINS`: Optional comma-separated list of additional exact frontend origins, such as Vercel preview domains.
- `MAX_UPLOAD_SIZE_MB` or `MAX_UPLOAD_MB`: Defaults to `5000` MB (5 GB decimal, or 5,000,000,000 bytes per file). The hosting provider, Cloudinary account plan, available memory, and document-processing workload can impose lower practical limits; see the deployment note below.
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: Required. An upload is only marked ready after its original is stored in Cloudinary and its text/chunks are saved in Neon.

The Vite frontend reads `VITE_API_BASE_URL` at build time. Set it in the Vercel project environment to the deployed FastAPI URL ending in `/api/v1` (for example, `https://your-backend.example/api/v1`). Do not use a localhost URL in Vercel. For local development, set `VITE_API_BASE_URL` to your local API URL, or set `VITE_DEV_API_PROXY_TARGET` to the local FastAPI origin when using the relative `/api/v1` default.

Set all service variables in the backend hosting provider as well as the appropriate Vercel variables. Local `.env` files do not configure deployed services.

For the current production frontend, set Render's `FRONTEND_URL` to `https://docu-ai-sage.vercel.app` (no trailing slash). That production origin is also included as a code fallback. Add extra preview origins to `FRONTEND_ORIGINS` as a comma-separated list if needed, then redeploy the Render service.

Ready-to-import production settings are in `backend/.env.render`; in Render, open the service's **Environment** page and choose **Add from .env**, select that file, then save and deploy. The file is gitignored because it contains credentials copied from the existing local environment. `frontend/.env.vercel` contains only the public API base URL. Vercel's dashboard does not import a `.env` file; add that single `VITE_API_BASE_URL` value under **Project Settings → Environment Variables** for Production (and Preview if needed), then redeploy.

The 5 GB setting is an application admission limit, not a guarantee that a 5 GB file can be processed on the current hosting and storage plans. If Render already has `MAX_UPLOAD_MB` or `MAX_UPLOAD_SIZE_MB` set, change that value to `5000` or remove it to use the default. Cloudinary requires chunked uploads above 100 MB and enforces plan-specific upload limits. The current API still accepts each upload in one HTTP request and processes document bytes synchronously; configure and verify the Render request/body limits, Cloudinary raw-file limits, service memory, and request timeout before relying on multi-gigabyte files. A robust multi-gigabyte workflow needs direct resumable client-to-object-storage uploads plus asynchronous extraction/indexing.

Install `backend/requirements.txt`, configure `DATABASE_URL` for Neon, then run `npm run migrate` from the repository root or `frontend/`. The command applies the Alembic migration version table and creates missing application tables and columns without dropping existing data. If a required column cannot be populated safely on existing records, the command stops and names the column rather than filling it with fake data.

Keep all secrets private. The application will not start without the database URL and JWT signing secret.

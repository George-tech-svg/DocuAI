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
- `MAX_UPLOAD_SIZE_MB` or `MAX_UPLOAD_MB`: Defaults to `10`.
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: Required. An upload is only marked ready after its original is stored in Cloudinary and its text/chunks are saved in Neon.

The Vite frontend reads `VITE_API_BASE_URL` at build time. Set it in the Vercel project environment to the deployed FastAPI URL ending in `/api/v1` (for example, `https://your-backend.example/api/v1`). Do not use a localhost URL in Vercel. For local development, set `VITE_API_BASE_URL` to your local API URL, or set `VITE_DEV_API_PROXY_TARGET` to the local FastAPI origin when using the relative `/api/v1` default.

Set all service variables in the backend hosting provider as well as the appropriate Vercel variables. Local `.env` files do not configure deployed services.

Install `backend/requirements.txt`, configure `DATABASE_URL` for Neon, then run `npm run migrate` from the repository root or `frontend/`. The command applies the Alembic migration version table and creates missing application tables and columns without dropping existing data. If a required column cannot be populated safely on existing records, the command stops and names the column rather than filling it with fake data.

Keep all secrets private. The application will not start without the database URL and JWT signing secret.

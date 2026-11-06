# Backend environment configuration

The backend reads `frontend/.env` (the credentials file already used by this
project) and then `backend/.env` if present. Values in `backend/.env` take
precedence. Neither file should be committed or included in a shared ZIP.

Required keys:

- `DATABASE_URL`: Complete Neon PostgreSQL connection URL.
- `JWT_SECRET_KEY`: A long, random signing secret.
- `DEEPSEEK_API_KEY`: Your DeepSeek API key for grounded chat answers.

Optional keys:

- `DEEPSEEK_MODEL`: Defaults to `deepseek-chat`.
- `FRONTEND_URL` or `FRONTEND_ORIGIN`: Defaults to `http://localhost:3000`.
- `MAX_UPLOAD_SIZE_MB` or `MAX_UPLOAD_MB`: Defaults to `10`.
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: Optional original-file storage.

Keep all secrets private. The application will not start without the database URL and JWT signing secret.

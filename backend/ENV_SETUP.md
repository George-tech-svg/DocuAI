# Backend environment setup

For the complete current architecture, API, feature, security, and operations guide, read [SYSTEM_DOCUMENTATION.md](../docs/SYSTEM_DOCUMENTATION.md).

## Vercel deployment

This repository deploys the React/Vite frontend and FastAPI backend as separate services in one Vercel project. The frontend calls `/api/v1` on the same domain, and root `vercel.json` routes `/api/*` to FastAPI. Leave `VITE_API_BASE_URL` unset for this setup.

Add backend values in Vercel Project Settings → Environment Variables. Select the appropriate Production, Preview, and Development environments, then redeploy. A local `.env` file does not configure Vercel. Do not import, commit, or share a file containing copied production credentials.

### Backend variables

| Variable | Use |
|---|---|
| `DATABASE_URL` | PostgreSQL/Neon connection string. Required. |
| `JWT_SECRET_KEY` | Private signing key for access tokens. Required. |
| `DEEPSEEK_API_KEY` | Server-side DeepSeek credential for follow-up query rewriting and answers. |
| `DEEPSEEK_MODEL` | Optional; defaults to `deepseek-flash`. |
| `GOOGLE_CLIENT_ID` | Google OAuth web client ID used to verify ID tokens. It is public configuration, not a client secret. |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary storage account name. |
| `CLOUDINARY_API_KEY` | Server-side Cloudinary key. |
| `CLOUDINARY_API_SECRET` | Server-only Cloudinary secret. |
| `ADMIN_BOOTSTRAP_CODE` | Private one-time code for first super-admin setup; use at least 16 characters and remove or rotate it after setup. |
| `MPESA_ENVIRONMENT` | `sandbox` by default; use `production` only with live Daraja credentials. |
| `MPESA_CONSUMER_KEY` | Server-only Daraja consumer key. |
| `MPESA_CONSUMER_SECRET` | Server-only Daraja consumer secret. |
| `MPESA_SHORTCODE` | Safaricom-assigned business shortcode for the Daraja transaction. Do not invent this value. |
| `MPESA_PASSKEY` | Server-only Daraja passkey paired with the shortcode/environment. |
| `MPESA_CALLBACK_BASE_URL` | Optional public HTTPS origin; defaults to `FRONTEND_ORIGIN`. |
| `MPESA_TRANSACTION_TYPE` | Optional; defaults to `CustomerPayBillOnline`. Match the Daraja shortcode setup. |
| `SUBSCRIPTIONS_ENFORCED` | Optional; defaults to `false`. Set `true` only after plans, live checkout, and callbacks are verified. |
| `FRONTEND_ORIGIN` or `FRONTEND_URL` | Public frontend origin used by CORS and callback fallback, without a trailing slash. `FRONTEND_URL` is an accepted alias. |
| `FRONTEND_ORIGINS` | Optional comma-separated additional frontend origins. |
| `MAX_UPLOAD_MB` or `MAX_UPLOAD_SIZE_MB` | Accepted aliases, but the application currently enforces a fixed 10 MB per-file cap. |
| `MAX_EXTRACTED_CHARS` | Optional extracted-text limit; capped at 5,000,000 characters. |
| `API_V1_PREFIX` | Optional API prefix; defaults to `/api/v1`. |

Never expose `DATABASE_URL`, `JWT_SECRET_KEY`, provider secrets, Daraja values, or `ADMIN_BOOTSTRAP_CODE` through `VITE_*` variables. The app currently does not need a Google client secret in the browser or backend for its ID-token verification flow.

### Google sign-in

Create a Google OAuth client of type **Web application**. Add the exact production domain as an Authorized JavaScript origin in Google Cloud Console; add `http://localhost:3000` when using the local Vite server. Set its client ID as backend `GOOGLE_CLIENT_ID` in Vercel and redeploy. The app obtains the configured public client ID from the backend; `VITE_GOOGLE_CLIENT_ID` is an optional fallback.

On the create-account screen, users can register with a password or continue with Google. Google verifies the email; the backend creates a Google-only account for a new email or reuses an existing account with that verified email. Google-only accounts have no password hash. There is no Google client secret for this credential flow.

### M-Pesa setup

Use the consumer key, consumer secret, shortcode, and passkey that Safaricom enabled together for the selected Daraja environment. `MPESA_SHORTCODE` is the Safaricom-assigned business shortcode, such as the configured PayBill or Till; it is not a number chosen by the developer. Set `MPESA_CALLBACK_BASE_URL` to a public HTTPS origin that can receive `/api/v1/billing/mpesa/callback/{token}`. The payment callback is required to confirm a payment; requesting an STK Push does not grant access by itself.

Keep `SUBSCRIPTIONS_ENFORCED=false` while validating plans and sandbox flows. The administrator must create an active plan. Only after testing confirmed, failed, and cancelled payment callbacks should you consider enforcing active subscriptions for uploads and chat.

### Local development

Use Python 3.12 (`backend/.python-version`) and install `backend/requirements.txt`. The backend reads the repository `frontend/.env` and `backend/.env`; process environment variables take priority. Never put backend secrets in `VITE_*` values. Run FastAPI from the `backend` directory:

```powershell
python -m uvicorn app.main:app --reload
```

Run the frontend from `frontend/` with `npm install` followed by `npm run dev`. Vite listens at `http://127.0.0.1:3000`. Set `VITE_DEV_API_PROXY_TARGET` to the local FastAPI origin, or set `VITE_API_BASE_URL` to a full local API prefix.

### Database migrations

With backend dependencies installed and `DATABASE_URL` configured, run `npm run migrate` from the repository root before using a fresh or updated backend. This applies Alembic migrations without dropping existing data. The current latest migration is `0012_document_chunk_fts_index.py`; it creates the PostgreSQL full-text index used by hybrid document retrieval.

### First administrator

Set `ADMIN_BOOTSTRAP_CODE` to a private random value of at least 16 characters in the backend environment. When no super administrator exists, the sign-in page’s small account-tools dot opens the one-time first-admin setup. The setup endpoint serializes concurrent attempts and closes after the first super administrator is created. Remove or rotate the code afterward. Public user registration cannot grant admin privileges.

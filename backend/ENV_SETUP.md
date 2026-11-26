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
- `GOOGLE_CLIENT_ID`: Google OAuth 2.0 Web application client ID used by the
  backend to verify Google ID tokens. It is not a client secret.
- `API_V1_PREFIX`: defaults to `/api/v1`.
- `MPESA_ENVIRONMENT`: optional; `sandbox` by default, or `production` after
  Safaricom has enabled the Daraja product for the shortcode.
- `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, and
  `MPESA_PASSKEY`: server-only Daraja credentials. Never add these as `VITE_*`
  variables or expose them to the frontend.
- `MPESA_CALLBACK_BASE_URL`: optional public HTTPS origin for Daraja callbacks;
  defaults to `FRONTEND_ORIGIN`.
- `MPESA_TRANSACTION_TYPE`: optional; defaults to `CustomerPayBillOnline`.
- `SUBSCRIPTIONS_ENFORCED`: optional; keep `false` while testing, then set
  `true` after live payments and plans have been verified to require active
  subscriptions for uploads and chat.

`APP_ENV`, `APP_NAME`, `APP_VERSION`, and `DEBUG` are retained from the
existing environment file for continuity; the API currently uses its own
application metadata defaults. No frontend API URL is needed for the shared
domain.

## Google sign-in

Create an OAuth 2.0 Client ID of type **Web application** in Google Cloud
Console, configure the consent screen, and add the production site origin
(`https://docuai-ljxe.vercel.app`) under Authorized JavaScript origins. If
`https://docuai-jet.vercel.app` is also an active site alias, add that origin
too. Add `http://localhost:5173` for local Vite development. Set the client ID in
backend `GOOGLE_CLIENT_ID`. The client ID is public; do not put a client
secret in the frontend. The app reads the public client ID from the backend,
so a `VITE_GOOGLE_CLIENT_ID` frontend build variable is optional. The backend
verifies Google's signed ID token and verified email before creating or
signing into a database account. Add `GOOGLE_CLIENT_ID` to Vercel's project
environment and redeploy. A frontend `VITE_GOOGLE_CLIENT_ID` can be set to the
same ID as an optional fallback.

Password-based and Google registrations require acceptance of the Terms of
Service and Privacy Notice. Password registration confirms both password
entries before it sends the account creation request. Google login and account
creation are separate actions; to register a new Google account, switch to
Create account, set and confirm a password, then accept the terms. That lets
the new account sign in with either Google or that password. `GOOGLE_CLIENT_ID`
can be exposed as a Config value in Vercel; it is a public OAuth client ID, not
a secret.

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

## Platform administration and billing

To register the first super administrator, set `ADMIN_BOOTSTRAP_CODE` to a
random private value of at least 16 characters in the backend environment.
The sign-in page then shows a tiny setup dot while no super administrator
exists. Open it, enter the private code, and register the first admin account.
The endpoint serializes setup requests and permanently closes after the first
super administrator is created. Keep this code out of frontend `VITE_*`
variables and rotate or remove it after setup. Normal public registration
cannot assign administrator privileges. `scripts/promote_admin.py` is a
restricted operational fallback and refuses to promote a second administrator.
Sign out and back in to load the Admin console.

Create one or more monthly plans in Admin → Plans. Monthly M-Pesa prompts are
sent only after the Daraja server credentials and shortcode are configured in
the backend environment. A plan renews after its payment callback is confirmed.
Use Daraja sandbox credentials for testing; configure the live shortcode and
production credentials separately before enabling `SUBSCRIPTIONS_ENFORCED`.
Local `.env` files do not configure Vercel; update the Vercel project
environment and redeploy after changing production variables.

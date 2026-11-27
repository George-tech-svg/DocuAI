# DocuMind AI — System Documentation

**Document purpose:** a practical guide to the product, features, architecture, setup, and operational limits currently represented in this repository.

**Last reviewed:** 27 November 2026  
**Repository baseline reviewed:** `956d8c9` (`Refresh full system documentation`).

> This guide describes the code in this repository. A feature can be implemented here and still need valid provider credentials, a database migration, a Vercel redeploy, or setup in a provider console before it works in production. No secret values belong in this document.

## Contents

1. [Product summary](#1-product-summary)
2. [People and permissions](#2-people-and-permissions)
3. [What users can do](#3-what-users-can-do)
4. [What administrators can do](#4-what-administrators-can-do)
5. [How the system is built](#5-how-the-system-is-built)
6. [Data stored](#6-data-stored)
7. [API reference](#7-api-reference)
8. [Third-party services](#8-third-party-services)
9. [Environment configuration](#9-environment-configuration)
10. [Deployment and database setup](#10-deployment-and-database-setup)
11. [Security and privacy behavior](#11-security-and-privacy-behavior)
12. [Limits and known operational considerations](#12-limits-and-known-operational-considerations)
13. [Repository map](#13-repository-map)
14. [Operational checklist](#14-operational-checklist)

## 1. Product summary

DocuMind AI is a web application for organizing documents and asking questions grounded in their contents. A member creates a private folder (called a knowledge base), uploads a supported document, waits for it to be indexed, then chats either about one selected document or across all ready documents in that folder. Conversations retain their search scope, and answers and conversations can be exported as PDFs.

The repository also includes email/password and Google authentication, a one-time first-administrator setup, a platform administration console, subscription plans, and Safaricom Daraja STK Push payment handling. Billing and account gating are configurable; a feature appearing in the interface does not by itself mean its external credentials and live merchant setup are ready.

### Main user journey

1. Register with an email and password, or continue with Google.
2. Sign in; the app keeps a signed session until sign-out or token expiry.
3. Create a folder in the workspace and upload PDF, TXT, DOCX, JPG, PNG, or HEIC files (10 MB per file by default).
4. The API stores the original in Cloudinary, queues indexing in PostgreSQL, then returns HTTP 202. A separate Render worker extracts text, runs OCR when needed, and builds search vectors. Follow the processing stage until the document becomes **Ready**.
5. Select a document or its folder, choose **This document** or **This folder**, ask a question, and review the answer and source excerpts.
6. Reopen saved conversations with their original scope or download an answer or conversation as a PDF.

Without a selected scope, the chat area explains both modes and how to find files. Folder scope requires at least one ready document. On desktop, the welcome message points to the left sidebar; on mobile, it tells the member to open the folder button at the top.

## 2. People and permissions

| Role | Capabilities |
|---|---|
| Visitor | View the sign-in/create-account screens and legal pages. |
| Member | Manage their own folders, documents, conversations, account settings, and billing details. Chat and upload access can optionally require an active paid subscription. |
| Platform administrator | All member functions plus platform overview, recent activity, member controls, subscription plan management, subscription review, payment review, and background-job monitoring/retry. |

There is a one-time bootstrap flow for the **first and only** super administrator. It uses a server-side `ADMIN_BOOTSTRAP_CODE`, serializes concurrent attempts, and closes once an administrator exists. Public registration cannot grant administrator privileges. The small account-tools dot at the upper-right of the sign-in screen opens administrator sign-in and, while available, first-administrator setup on desktop and mobile.

The admin dashboard’s integration indicators report whether required configuration values/dependencies are present. They are configuration checks, not live end-to-end tests of Google, DeepSeek, Cloudinary, or Daraja.

## 3. What users can do

### 3.1 Accounts and sessions

- Email/password account creation collects name, email, password, and confirmation; client-side checks cover required fields, email shape, matching passwords, and an eight-character minimum. Terms and Privacy acceptance is required. Success is shown on the sign-in form after registration.
- Passwords are stored as password hashes, not as readable passwords.
- Google Identity Services provides the browser sign-in button. The backend verifies the signed Google ID token against the configured OAuth client ID and requires a verified email.
- A Google sign-in with a verified email that matches an existing password account signs into that account, preventing an email duplicate. A Google-only account has no password hash.
- Google account creation is offered on the create-account form and requires Terms/Privacy acceptance. A new verified Google email creates a Google-only account; a matching existing account is reused. A new Google account can also be created through the Google sign-in API path, so one verified email still maps to one database account.
- The sign-in page shows errors and loading feedback. The backend uses **“Incorrect email or password. Please try again.”** for both unknown emails and incorrect passwords to reduce account discovery; Google-only accounts receive **“This account was created with Google. Please sign in with Google.”**
- A signed JWT is held in browser local storage. The current token lifetime in code is 24 hours; a valid session is checked against the server when the app loads. Sign-out clears the local session and returns to the sign-in page.
- An administrator signs in using the administrator account’s normal email and password, then opens the admin console from account tools.
- Registration and login show inline errors, success feedback, and disabled/loading buttons while requests are running. Network failures are shown as readable messages. Unknown email and wrong password intentionally share one login message; this is different from the older requested wording that distinguished those cases.

### 3.2 Workspace, folders, and documents

- Each member can create, rename, pin, archive, and delete their own knowledge bases and documents. Folder/document ownership is checked by the backend.
- Upload UI and validation allow **PDF, TXT, DOCX, JPG, PNG, and HEIC**. Each source file has a configurable per-file cap (`MAX_UPLOAD_MB`, 10 MB by default; service hard ceiling 50 MB). Several selected JPG/PNG photos are combined in selection order into one PDF before upload. Mobile includes a photo picker and a **Take photo** control with the environment-camera capture hint.
- Documents have `pending`, `processing`, `ready`, or `failed` status and a processing stage (`uploading`, `extracting`, `ocr`, `embedding`, or `ready`). The browser polls while work is active and shows the current stage.
- pypdf extracts PDF text; python-docx reads Word paragraphs and tables; TXT is decoded as UTF-8. Sparse PDF pages and image files use per-page OCR with Tesseract `eng+swa`. HEIC is converted to JPEG in memory for OCR. One page failing OCR does not stop other pages. Documents store whether OCR ran and average OCR confidence; the UI warns below 60% or when OCR confidence is unavailable.
- Upload instructions explain supported types, the configured size limit, and that clear scans/photos work best. Errors identify invalid or mismatched types, oversized files, unreadable files, and server-side processing failures.
- Before deleting a document or folder, the app checks the saved conversation count and names the history that will be lost. The user can cancel, download the affected conversations together as a PDF and then delete, or delete anyway. A failed history download prevents deletion.
- The backend extracts text, divides it into overlapping passages, creates vector embeddings, and stores passages for retrieval. The original file is stored in Cloudinary; an unavailable or failing storage provider causes processing to fail with a visible explanation.
- The upload request stores the original in Cloudinary, saves a pending document row, and inserts an `index_document` job in PostgreSQL in the same transaction. The job payload contains only the document ID; the worker fetches the original through its saved Cloudinary URL. The API returns HTTP 202 after accepting the work and does no indexing in the web request.
- The separate Render worker claims jobs with `SELECT ... FOR UPDATE SKIP LOCKED`, preventing concurrent workers from claiming the same available row. It refreshes a 10-minute lease while working; jobs from a crashed worker can be reclaimed after lease expiry.
- Jobs allow four attempts by default. Failures store a short user-readable error and retry after exponential delays (30, 60, and 120 seconds); exhausted jobs become failed. The admin Jobs area shows queue counts and the last 50 failures and can queue a failed document again.
- The worker needs Tesseract with English and Swahili language data, PyMuPDF, Pillow, pytesseract, pillow-heif, and libheif. These are installed by the worker requirements file and Render build command. The Vercel backend only accepts/stores uploads and enqueues jobs; it does not run OCR/indexing.
- Files are shown in the sidebar. On mobile, the folder list opens from the folder button; selecting a file closes the drawer.
- Workspace layout adapts to mobile and desktop. The scope switch is a keyboard-operable segmented control above the message box. Switching from folder scope to a file through the sidebar asks for confirmation; choosing a scope directly in the control is explicit and does not need a second confirmation.

### 3.3 Chat and saved history

- Chat uses an explicit scope: `scope_type=document` with the selected document UUID, or `scope_type=folder` with the folder/knowledge-base UUID. The backend rejects a missing or invalid scope and rejects folder scope when there are no ready documents. Both retrieval paths apply the same ownership, ready-state, and scope filters.
- For every question, the backend runs vector similarity and PostgreSQL full-text keyword search for up to 20 candidates from each path, merges their rankings with reciprocal-rank fusion (constant 60), deduplicates by passage UUID, and uses the top five. If keyword search returns no matches, it uses vector results alone. Logs identify `hybrid` or `vector-only` and report how many of the final passages appeared in each ranking. PostgreSQL’s built-in text search and a GIN index are used; no external search service is involved.
- On a follow-up, the backend loads up to the eight most recent conversation messages and asks DeepSeek to rewrite the latest question as a short standalone search query before retrieval. It uses the rewritten query only for embeddings and retrieval, then answers using the original question plus retrieved passages. Rewriting is best effort: missing configuration, provider/network errors, or an empty rewrite fall back to the original question. The effective query is stored as `search_query` in the user message’s JSON metadata; the original wording remains the saved message content. This behavior applies to document and folder scope.
- The system instruction asks for a useful title, clear subheadings and bullets when helpful, plain language, short sentences, simple explanations of necessary technical words, and citations such as `[1]`. It tells the model to say when the source does not answer the question and to treat document text as evidence, not instructions.
- Answers are rendered as readable Markdown-like headings, lists, emphasis, and code. Source excerpts carry the document name, page number when available, and excerpt text. Folder-scope answers identify the number of source documents used.
- Questions and answers are stored in conversations associated with the user and selected scope. Reopening a conversation restores its document or folder scope. The sidebar can reopen, rename, pin, archive, or delete conversations. Conversation endpoints verify ownership.
- Every download action currently exposed by the app produces an A4 PDF: one assistant answer, one conversation with source excerpts, or multiple saved conversations during a document/folder deletion confirmation. The app has no download action for original uploads or a general data export.
- If no valid scope is selected, the welcome message explains both modes and where to find files. Folder chat shows a clear no-ready-documents message and is also rejected by the backend when the folder has no ready documents.

### 3.4 Account settings and billing

- Account settings show the signed-in name and email, link to Plan & Billing, provide legal pages, and include sign-out.
- Members can view active plans, current/pending subscription status, and recent payment requests. A Kenyan mobile number is normalized and validated before checkout.
- A member can start an STK Push against an active plan. The plan starts only after the payment callback confirms success. Pending prompts are not counted as paid access.
- If a member paid but still has no access, they can submit a recovery request with their phone number, local payment date/time, and M-Pesa confirmation text or receipt. Only one request may be pending per member. The form stores evidence and status; it never grants access.
- Members can see whether each request is pending, granted, or rejected, including the rejection reason.
- An active subscription requirement is controlled by `SUBSCRIPTIONS_ENFORCED`. It defaults to `false`; when enabled, uploads and chat require a currently active subscription. Administrators bypass this check.

### 3.5 User-facing errors and confirmations

Forms and request flows display errors in the interface instead of failing silently. Common current messages include:

| Situation | Message |
|---|---|
| Required registration fields missing | `Please fill in all fields.` |
| Invalid email format | `Please enter a valid email address.` |
| Password confirmation mismatch | `Passwords do not match. Please check and try again.` |
| Password below eight characters | `Password must be at least 8 characters long.` |
| Duplicate password account | `An account with this email already exists. Please log in.` |
| Registration email already belongs to Google | `This email is already registered with Google. Please sign in with Google.` |
| Empty login fields | `Please enter both email and password.` |
| Unknown email or incorrect password | `Incorrect email or password. Please try again.` |
| Google-only account used on password login | `This account was created with Google. Please sign in with Google.` |
| Invalid upload type | `Invalid file type. Please upload a PDF, TXT, DOCX, JPG, PNG, or HEIC file.` |
| Upload larger than the configured per-file limit | `File is too large. Maximum size is 10MB.` at the default setting; the number follows `MAX_UPLOAD_MB`. |
| Folder chat with no ready documents | `This folder has no ready documents yet. Upload a PDF, TXT, DOCX, JPG, PNG, or HEIC file and wait until it is ready before chatting.` |
| Generic server failure | `Something went wrong on our end. Please try again later.` |
| Network failure | `Network error. Please check your connection and try again.` |

The API client also reports request timeouts, and upload processing errors include a plain-language cause where one is available. Delete confirmations show how many conversations will be removed and provide **Cancel**, **Download conversations as PDF then delete**, and **Delete anyway** choices.

## 4. What administrators can do

The Admin console has the following areas:

| Area | Current capability |
|---|---|
| Overview | Counts members, document states, conversations, questions, weekly questions, subscriptions, payment states, confirmed revenue, and configured integration readiness. |
| Members | List up to 1,000 members with account and plan status; enable or disable member accounts. The current admin cannot disable their own account from this screen. |
| Activity | Show up to 60 recent metadata events drawn from the latest registrations, uploads, chatbot questions, and payments. The feed does not include question text, answer text, or document contents. |
| Plans | Create plans; edit a plan’s price; publish or hide it; set its name, description, duration, and price. |
| Subscriptions | Review subscriptions and cancel an active subscription. |
| Payments | Review up to 1,000 payment records, phone number, status, receipt, and provider description. |
| Payment recovery | Review member claims and suggested matches against payments already recorded by Daraja checkout. An administrator must explicitly choose a plan and grant access, or enter a rejection reason. Decisions are recorded with the acting administrator, request, selected payment/plan, action, reason, and timestamp in the audit table. |
| Jobs | View counts for queued, running, done, and failed indexing jobs; inspect the most recent 50 failures and their user-readable errors; enqueue a failed indexing job again. |

The admin page is protected by the backend superuser flag; hiding or showing its entry point in the browser is not the authorization control. Admin activity and member data are presented in the responsive admin interface. Billing uses a muted neutral surface with readable cards and alert colors; the overall workspace and auth screens also use responsive styling.

This activity view is computed from current database records, not a separate immutable audit log. It is therefore an operational recent-activity view, not a complete record of every change ever made.

## 5. How the system is built

| Layer | Technology and responsibility |
|---|---|
| Browser application | React 18, TypeScript, and Vite. Contains authentication, workspace, chat, PDF export, billing, and admin screens. |
| API | FastAPI on Python 3.12, with versioned endpoints under `/api/v1`. |
| Database | PostgreSQL (configured for Neon) with SQLAlchemy and Alembic migrations. `pgvector` stores 384-dimensional document vectors and performs similarity search. |
| Authentication | Signed JWT bearer tokens; Argon2-backed password hashing through `pwdlib`; Google ID-token verification through `google-auth`. |
| Document indexing | A PostgreSQL jobs table feeds a Render worker. pypdf/PyMuPDF extract and render PDFs; python-docx reads Word files; Pillow reads images; Tesseract performs `eng+swa` OCR; text is split into passages; FastEmbed runs a quantized MiniLM-L6-v2 embedding model. |
| Answer generation | DeepSeek chat completions API, default model name `deepseek-flash`. |
| Original file storage | Cloudinary raw-file storage. Text passages and vectors are stored in PostgreSQL. |
| Payments | Safaricom Daraja OAuth and M-Pesa STK Push API; a public callback updates payment and subscription records. |
| Hosting/routing | `vercel.json` defines separate frontend and backend services. Same-domain `/api/*` requests are routed to FastAPI; all other paths go to the Vite frontend. |

The FastEmbed model is loaded lazily in the worker process so simple API health checks do not load it. The Render build preloads and validates its local model cache; the first job after a fresh worker build therefore does not need to download the model. The Vercel API only validates/stores uploads and enqueues jobs; a separate Render worker performs extraction, OCR, chunking, and embeddings.

## 6. Data stored

The primary application tables are:

| Table/entity | Purpose |
|---|---|
| `users` | Name, unique email, optional password hash, active/verified flags, superuser flag, timestamps. Google-only users have a null password hash. |
| `knowledge_bases` | User-owned folder name, description, active/archive/pin flags, timestamps. |
| `documents` | Folder link, original filename, type/size, Cloudinary identifier and URL, processing state/stage, OCR-used flag/confidence, page/chunk counts, errors, archive/pin flags, timestamps. |
| `jobs` | PostgreSQL JSONB payload, type/status, attempts/maximum attempts, next run time, worker lease/identity, safe last error, and timestamps. A status/run-time index supports queue polling. |
| `document_chunks` | Extracted passage, page number, order, 384-value vector. A PostgreSQL GIN expression index supports built-in full-text search. |
| `conversations` | Owner, folder/document links, explicit `scope_type` (`folder` or `document`), title, archive/pin flags, timestamps. |
| `messages` | Conversation, role, original body, sequence, source metadata, model metadata, optional JSON metadata (including the effective `search_query` for user turns), timestamp. |
| `subscription_plans` | Plan name, description, price in KSh, duration, active status. |
| `subscriptions` | User, plan, status, start/expiry dates. |
| `mpesa_payments` | User/subscription, amount, phone, status, Daraja request IDs, receipt, callback token, result details, timestamps. |
| `payment_recovery_requests` | Member-submitted phone, payment time and M-Pesa message/receipt, review status, optional matched payment, resulting subscription, reviewer, reason/note, and timestamps. |
| `admin_audit_logs` | Administrator actions for payment recovery, including actor, request, action, reason, details, and timestamp. |

The unique email constraint enforces one account per email. Foreign keys and ownership queries constrain member access. Deleting a document removes conversations scoped to that document; deleting a folder removes its folder-scoped conversations and contained documents. The UI requires a confirmation before either delete flow and can download affected conversations as a combined PDF first. Deleting an account cascades its owned records according to the database relationships.

## 7. API reference

All routes below are under `/api/v1`. Unless noted as public/callback, routes require a bearer token. Admin routes additionally require a superuser account. Exact request/response schemas are defined in `backend/app/schemas/` and endpoint code.

| Method and route | Access | Purpose |
|---|---|---|
| `GET /health` | Public | Basic API health response. Does not test every third-party integration. |
| `GET /auth/google/config` | Public | Returns whether Google sign-in is configured and the public client ID. |
| `GET /auth/admin/bootstrap/status` | Public | Returns whether first-admin setup is configured/available and whether an admin exists; never returns the setup code. |
| `POST /auth/admin/bootstrap` | Public, one-time guarded | Set up/promote the first administrator using the backend bootstrap code. |
| `POST /auth/register` | Public | Create an email/password user. |
| `POST /auth/login` | Public | Verify email/password and issue a JWT. |
| `POST /auth/google` | Public | Verify a Google ID token, create or match the user, and issue a JWT. |
| `GET /auth/me` | Member | Return the current user profile. |
| `GET /knowledge-bases`, `POST /knowledge-bases` | Member | List or create folders. |
| `GET /knowledge-bases/{kb_id}`, `PATCH /knowledge-bases/{kb_id}`, `DELETE /knowledge-bases/{kb_id}` | Owner | Read, update, or delete a folder. |
| `GET /knowledge-bases/{kb_id}/documents` | Owner | List documents and states for a folder. |
| `GET /knowledge-bases/{kb_id}/documents/upload-config` | Owner | Return the configured size limit and accepted file extensions for the upload UI. |
| `POST /knowledge-bases/{kb_id}/documents` | Member / subscription gate if enabled | Store a PDF/TXT/DOCX/image original in Cloudinary, create a document, enqueue indexing, and return HTTP 202. |
| `GET /knowledge-bases/{kb_id}/documents/{doc_id}/status` | Owner | Read state/stage, OCR use/confidence/warning, counts, and processing error. |
| `PATCH /knowledge-bases/{kb_id}/documents/{doc_id}` | Owner | Update document display/archive/pin fields. |
| `DELETE /knowledge-bases/{kb_id}/documents/{doc_id}` | Owner | Delete the document and its associated conversations; attempts Cloudinary deletion first. |
| `POST /chat` | Member / subscription gate if enabled | Accept `scope_type`, `scope_id`, question, and optional conversation ID. Run retrieval only inside the owned document or folder scope, answer with the original question, then persist the exchange and retrieval-query metadata. |
| `GET /conversations` | Member | List the current user’s saved conversations. |
| `GET /conversations/{id}/messages` | Owner | Read saved messages, source metadata, and per-message metadata such as the search query used. |
| `PATCH /conversations/{id}` | Owner | Rename, archive, or pin a conversation. |
| `DELETE /conversations/{id}` | Owner | Delete a conversation. |
| `GET /billing/plans` | Public | List active subscription plans. |
| `GET /billing/me` | Member | Read own current/pending subscription and recent payments. |
| `POST /billing/checkout` | Member | Create a payment/subscription request and send an STK Push. |
| `GET /billing/payment-recovery` | Member | List own submitted recovery requests and their review status. |
| `POST /billing/payment-recovery` | Member | Submit M-Pesa phone, payment time, and message/receipt as a pending request; does not grant access. |
| `POST /billing/mpesa/callback/{callback_token}` | Daraja callback | Validate the callback token/request and update payment/subscription state. |
| `GET /admin/overview` | Admin | Platform and configuration counts. |
| `GET /admin/activity` | Admin | Recent activity metadata. |
| `GET /admin/members`, `PATCH /admin/members/{user_id}` | Admin | List and enable/disable member accounts. |
| `GET /admin/plans`, `POST /admin/plans`, `PATCH /admin/plans/{plan_id}` | Admin | Manage subscription plans. |
| `GET /admin/subscriptions`, `PATCH /admin/subscriptions/{subscription_id}` | Admin | Review/cancel subscriptions. |
| `GET /admin/payments` | Admin | Review payment records. |
| `GET /admin/payment-recovery` | Admin | List recovery requests and suggested matches against stored Daraja payment records. |
| `POST /admin/payment-recovery/{request_id}/review` | Admin | Explicitly grant access for a selected plan or reject with a required reason; writes an audit record atomically with the decision. |
| `GET /admin/payment-recovery/audit` | Admin | List recent payment-recovery decisions and the administrator who made them. |
| `GET /admin/jobs` | Admin | Read queue counts and the last 50 failed jobs. |
| `POST /admin/jobs/{job_id}/retry` | Admin | Requeue a failed document job and reset its attempt/error state. |

For `POST /chat`, send `scope_type: "document"` with `scope_id` set to a document UUID, or `scope_type: "folder"` with `scope_id` set to a knowledge-base UUID. `conversation_id` is optional for a new chat; when supplied, it must belong to the signed-in user and match the requested scope. The response contains the answer, saved conversation ID, and source list (document ID/name, page when known, and excerpt). Saved user messages expose `metadata.search_query` from the messages endpoint.

## 8. Third-party services

### Google Identity

The frontend uses Google Identity Services to obtain an ID credential. The backend independently verifies the token and its audience with `GOOGLE_CLIENT_ID`, then accepts only an identity with a verified email and subject. Configure the exact production domain as an authorized JavaScript origin in Google Cloud Console. Add localhost if testing locally. The client ID is public configuration; no Google client secret is used by this flow.

### DeepSeek

The backend sends recent conversation turns and the latest follow-up to DeepSeek when it needs to rewrite a follow-up for retrieval. It sends the original question and retrieved document passages to DeepSeek to generate the answer. Both calls use the server-side API key. The model can be set with `DEEPSEEK_MODEL`; the code default is `deepseek-flash`. The rewrite is best effort and falls back to the original query after a failure or empty response. The AI integration indicator only checks whether an API key is present. Provider quotas, network access, model availability, and key validity remain external dependencies.

### Cloudinary

The original uploaded file is placed in a `documind` Cloudinary folder as a raw resource. Configure cloud name, API key, and API secret on the backend only. Cloudinary is also called when an original file is deleted. If Cloudinary is not configured or rejects an upload, indexing is marked failed rather than pretending the original file was stored.

### Safaricom Daraja / M-Pesa

The backend obtains a Daraja OAuth access token and requests a customer STK Push. `MPESA_SHORTCODE` must be a shortcode assigned/enabled for the Daraja app and transaction type (for example, the business PayBill/Till configuration Safaricom supplies); it is not an arbitrary number chosen by the developer. The callback URL must be reachable over public HTTPS. In production, use the production Daraja environment and production credentials, shortcode, and passkey supplied for that shortcode. A successful callback is what activates paid access; a prompt being sent or accepted by the API is not itself payment confirmation.

`mpesa_ready` means the application sees a consumer key, consumer secret, shortcode, passkey, and callback base URL (or fallback frontend origin). It does not prove Safaricom accepts the credentials or that the callback succeeds. Confirm all values belong to the same Daraja app/environment and redeploy after changing Vercel variables.

Payment recovery matching is a **suggestion** against Daraja payments already stored in this database. It compares the supplied receipt text with stored receipts and also looks for the same phone number within 24 hours of the supplied payment time. It does not query Safaricom’s transaction history, and a suggested match is not proof of payment. The administrator must reconcile the claim and make an explicit decision. A PayBill/Till payment that was never recorded by the app will not appear as a candidate; the admin can still review the supplied evidence and manually grant a chosen plan.

## 9. Environment configuration

Set these as **backend/server** variables in Vercel Project Settings → Environment Variables. Do not put backend secrets in `VITE_*` variables or browser code. Apply changes to the relevant environment (Production/Preview/Development) and redeploy.

| Variable | Required/use | Notes |
|---|---|---|
| `DATABASE_URL` | Required | PostgreSQL/Neon connection URL. Keep private. |
| `JWT_SECRET_KEY` | Required | Long random signing secret for login tokens. Keep private. |
| `DEEPSEEK_API_KEY` | Needed for AI answers | Provider credential; server only. |
| `DEEPSEEK_MODEL` | Optional | Defaults to `deepseek-flash`. |
| `GOOGLE_CLIENT_ID` | Needed for Google sign-in | Public OAuth web client ID; also register the exact site origins in Google Cloud Console. Not a client secret. |
| `CLOUDINARY_CLOUD_NAME` | Needed for original-file storage | Cloudinary account setting. |
| `CLOUDINARY_API_KEY` | Needed for original-file storage | Server-side key. |
| `CLOUDINARY_API_SECRET` | Needed for original-file storage | Server-only secret. |
| `ADMIN_BOOTSTRAP_CODE` | Needed only for first admin setup | Use a strong private random value (setup form requires at least 16 characters); remove/rotate after creating the first admin. |
| `MPESA_ENVIRONMENT` | Needed for M-Pesa | `sandbox` by default; use `production` only with live Daraja credentials and shortcode. |
| `MPESA_CONSUMER_KEY` | Needed for M-Pesa | Daraja app consumer key; server only. |
| `MPESA_CONSUMER_SECRET` | Needed for M-Pesa | Daraja app consumer secret; server only. |
| `MPESA_SHORTCODE` | Needed for M-Pesa | Safaricom-assigned business shortcode configured for the Daraja transaction. |
| `MPESA_PASSKEY` | Needed for STK Push | Daraja passkey paired with the shortcode/environment. |
| `MPESA_CALLBACK_BASE_URL` | Needed for reliable callbacks | Public HTTPS app origin. For the current Vercel site, confirm the active domain and use that origin; do not rely on the stale code fallback. |
| `MPESA_TRANSACTION_TYPE` | Optional | Defaults to `CustomerPayBillOnline`; confirm whether this is appropriate for the assigned PayBill/Till configuration. |
| `SUBSCRIPTIONS_ENFORCED` | Optional | Defaults to `false`. Set to `true` only after plans, live payments, and callbacks have been verified. |
| `FRONTEND_ORIGIN` / `FRONTEND_URL` | Recommended | Public frontend origin used by CORS and as callback fallback. `FRONTEND_URL` is an accepted alias. Use the active deployed domain without a trailing slash. |
| `FRONTEND_ORIGINS` | Optional | Additional comma-separated allowed frontend origins. |
| `MAX_UPLOAD_MB` / `MAX_UPLOAD_SIZE_MB` | Optional setting | Per-file upload limit in MB; defaults to 10 and is clamped between 1 and the service ceiling of 50 MB. Set the same value for the Vercel API and Render worker. A host proxy may enforce a lower request limit. |
| `MAX_EXTRACTED_CHARS` | Optional | Extracted-text bound; code caps it at 5,000,000 characters. |
| `JOB_POLL_SECONDS` | Render worker optional | Seconds between queue polls when no job is ready; defaults to 3. |
| `API_V1_PREFIX` | Optional | Defaults to `/api/v1`. Change only if routes and callback construction are intentionally reconfigured together. |

The frontend normally uses the same-domain `/api/v1` path. `VITE_API_BASE_URL` is only for a frontend pointed to a separate API; leave it unset for the Vercel same-domain rewrite. Local development can use `VITE_DEV_API_PROXY_TARGET` or a local `VITE_API_BASE_URL`.

### Current production configuration notes

- Use the actual production domain shown in the Vercel project. Configure `FRONTEND_ORIGIN`, Google authorized origins, and `MPESA_CALLBACK_BASE_URL` to match it; do not rely on an old example or a stale default hostname.
- The billing page saying “M-Pesa checkout is not enabled yet” indicates one or more required backend values are absent from the running deployment. The dashboard’s “Ready” state only checks that values exist. Check variable names, Vercel environment scope, shortcode, callback origin, and redeployment; never paste secret values into support messages.
- The admin overview configuration flags are not connectivity probes. A green “Configured” indicator does not guarantee provider credentials are valid.

## 10. Deployment and database setup

### Vercel deployment

`vercel.json` describes two services: Vite frontend and FastAPI backend. It rewrites `/api/*` to the backend and the remaining routes to the frontend. It sets `Cross-Origin-Opener-Policy: same-origin-allow-popups` for Google popups and disables caching for the app entry pages while allowing hashed assets to be cached immutably. The Vercel API validates/stores uploads and queues work; it does not perform indexing or OCR during an API request.

The root `render.yaml` defines a separate long-lived Render Background Worker running the same backend repository code. Set its `DATABASE_URL` to the exact same PostgreSQL/Neon database URL used by the Vercel backend. Do not deploy `backend/worker.py` as a Vercel Function.

After adding or changing backend environment variables, redeploy the relevant Vercel deployment. A local `.env` does not change Vercel settings. The Vercel build preloads the embedding model under the backend service and validates its 384-dimensional output. The Render worker installs `requirements-worker.txt`, installs `tesseract-ocr`, `tesseract-ocr-eng`, `tesseract-ocr-swa`, and `libheif-dev`, and runs `scripts/preload_embedding_model.py` as part of the build.

### Database migrations

The SQLAlchemy schema is migrated with Alembic. Run `npm run migrate` from the repository root after pulling a change that adds or modifies a database table/column and before using that backend version. The migration script invokes Alembic from the backend directory. Migration history is in `backend/migrations/versions/`; current migrations include the initial schema, compatibility fixes for an existing Neon database, archive/pin fields, plans/payments, Google-only nullable passwords, payment recovery/audit tables, conversation scope, per-message search metadata, the PostgreSQL full-text GIN index, and durable jobs/OCR columns. The latest repository migration is `0013_durable_jobs_and_ocr.py`.

Do not run ad-hoc SQL to create the first administrator. Use the first-admin setup page and configured bootstrap code. The database migration is not a substitute for Google, Cloudinary, DeepSeek, or Daraja configuration.

### Local development

- Python must be 3.12 (project metadata requires `>=3.12,<3.13`). Install backend dependencies from `backend/requirements.txt` or the project metadata.
- Install frontend dependencies in `frontend/`; run the Vite development server with `npm run dev`.
- The backend settings load repository `frontend/.env` and `backend/.env` (shell environment variables take precedence). Never commit either env file or place server secrets in frontend env files.
- Configure a development API proxy or `VITE_API_BASE_URL` as described above.
- Apply migrations before using the app against a fresh or changed database.
- For asynchronous indexing locally, install `backend/requirements-worker.txt`, install Tesseract with `eng` and `swa` data plus libheif, set backend environment values, then run `python backend/worker.py` in a separate long-lived terminal. Run `python backend/worker.py` only after applying migration `0013`.

## 11. Security and privacy behavior

- Password hashes use the recommended `pwdlib` password hashing implementation; plaintext passwords are not stored.
- JWTs are signed with `JWT_SECRET_KEY`, expire after 24 hours, and are sent as bearer tokens to protected API routes.
- Backend authorization checks active user state, admin status, and object ownership. Optional subscription checks happen on upload/chat when enabled.
- Google ID tokens are verified server-side, including the configured audience and verified email. The client ID is not a secret; the backend does not need a Google client secret for this credential flow.
- Daraja consumer credentials, passkey, database URL, JWT key, DeepSeek key, Cloudinary secret, and admin bootstrap code are server secrets. Never expose them through `VITE_*`, the browser, screenshots, logs, or committed files.
- Admin activity summaries omit actual chat questions and document content, although the feed includes a member’s name/email and event metadata.
- User document and conversation access is scoped to the authenticated owner. Admin APIs are protected by a database superuser flag.
- The `health` route only confirms that the API route is responding. It does not verify database migrations or external services.

## 12. Limits and known operational considerations

1. **Upload size and host proxy:** the configured per-file cap defaults to 10 MB and can be changed with `MAX_UPLOAD_MB` up to the service hard ceiling of 50 MB. Vercel or another host may impose a lower request-body limit. Confirm the deployment limit if files near the configured maximum fail before reaching FastAPI.
2. **Photo combination:** the browser combines multiple JPG/PNG selections into one PDF in order. HEIC uploads are supported for OCR, but the browser does not combine several HEIC files into a single PDF; select camera photos as JPG/PNG to combine them.
3. **OCR quality:** OCR can misread blurred, rotated, low-resolution, handwritten, or complex-layout pages. The confidence warning is a guidance signal, not a guarantee that every word is correct. Review important text against the original.
4. **Worker availability:** accepted uploads remain queued if the Render worker is stopped. Configure an alert/restart policy and inspect the admin Jobs section. The same database must be configured for API and worker; changing the schema requires migration `0013` before deployment.
5. **Provider reliability:** chat generation, Google token verification, Cloudinary storage, M-Pesa checkout/callback, and OCR depend on external services or worker packages/system data and correct configuration.
6. **Google error diagnosis:** browser messages about Cross-Origin-Opener-Policy can be informational depending on popup behavior; an `/auth/google` 500 is a backend issue. Read the HTTP response and Vercel backend logs; confirm `GOOGLE_CLIENT_ID`, Google authorized origins, deployed `google-auth` dependency, database connectivity, and applied migrations. Do not treat the browser COOP warning alone as proof of a failed configuration.
7. **Payment activation:** do not enable enforced subscriptions until an active plan, valid live Daraja setup, public callback, successful payment confirmation, and reconciliation process have been checked.
8. **Recent activity retention:** the activity feed queries recent underlying records; it is not a separate permanent audit/event ledger.
9. **Product QA:** code documentation is not proof that every external account, production secret, callback, or deployed environment has been independently verified. Use the checklist below for a real production readiness pass.

## 13. Repository map

```text
frontend/
  src/App.tsx                 Main application, login/register, workspace and chat UI
  src/AdminDashboard.tsx      Platform administration UI
  src/BillingPage.tsx         Member plan and payment UI
  src/GoogleSignIn.tsx        Google Identity Services button and credential callback
  src/AssistantMessage.tsx    Readable rendering of structured answer text
  src/pdfExport.ts            Answer and saved-conversation PDF generation
  src/style.css               Application layout, responsive styles, and visual themes
backend/
  worker.py                   Long-running Render job poller and processor
  requirements-worker.txt     OCR/PDF/image worker dependencies
  app/api/v1/endpoints/       FastAPI auth, folder, file, chat, admin, billing endpoints
  app/services/               Auth, extraction/OCR, indexing, job queue, retrieval, AI, storage, Daraja
  app/models/entities.py      Database entities and relationships
  app/schemas/                API validation and response schemas
  app/core/config.py          Environment settings and fixed upload/extraction caps
  migrations/versions/        Alembic database schema history
render.yaml                   Render Background Worker deployment blueprint
scripts/
  migrate.mjs                 Repository-level migration command
vercel.json                   Vercel service routing and response headers
README.md                     Project start and deployment overview
backend/ENV_SETUP.md          Existing environment and deployment notes
```

## 14. Operational checklist

### Before a production release

- [ ] Confirm Vercel frontend and backend services both build from the intended branch/commit.
- [ ] Apply the latest Alembic migration to the production database.
- [ ] Create the Render Background Worker from `render.yaml`; set `DATABASE_URL` to exactly the same database used by Vercel, and set the same `MAX_UPLOAD_MB` value and a strong `JWT_SECRET_KEY`.
- [ ] Confirm the Render build installed Tesseract, `eng` and `swa` language data, and libheif; confirm the worker starts and remains online.
- [ ] Upload a normal PDF, a scanned PDF, a DOCX, a JPG/PNG photo, and a HEIC photo; confirm HTTP 202, queue completion, progress stages, OCR confidence, and an answer grounded in the indexed document.
- [ ] Stop the worker briefly, upload a test file, restart the worker, and verify the queued job is reclaimed and completed. Exercise retry and terminal failure from the admin Jobs area.
- [ ] Confirm the production origin is consistent across `FRONTEND_ORIGIN`, CORS, Google authorized origins, and Daraja callback base URL.
- [ ] Confirm the Google web client ID and its authorized origin; test both new-account and existing-account Google sign-in.
- [ ] Confirm a private first-admin code was used once, then remove or rotate it; test admin sign-in and ensure public users cannot access admin endpoints.
- [ ] Confirm DeepSeek key/model with a real document question and inspect graceful provider errors.
- [ ] Confirm Cloudinary credentials with upload and delete of a non-sensitive test file.
- [ ] Confirm Daraja environment, assigned shortcode, consumer credentials, passkey, transaction type, and public callback URL all belong together.
- [ ] Create and activate at least one subscription plan; complete a sandbox payment before moving to production Daraja credentials.
- [ ] Verify the callback marks a successful payment paid and activates the corresponding subscription; verify failed/cancelled callbacks do not grant access.
- [ ] Submit a member payment recovery request and confirm it stays pending; review a candidate match, manually grant or reject, and verify the audit record and member-visible result.
- [ ] Decide whether to set `SUBSCRIPTIONS_ENFORCED=true` only after payment flow verification.
- [ ] Test every accepted file type, invalid type, configured size limit, OCR fallback/low-confidence warning, worker retry/failure, chat without selected file, chat answer citations, conversation history, and PDF export.
- [ ] Test the registration, login, workspace, billing, and admin screens on narrow mobile and desktop widths.
- [ ] Check Vercel backend logs for unhandled errors and verify secrets are not printed in them.

## 15. Phase 2: important dates and reminders

After a document becomes ready, the Render worker queues an `extract_events` job. The job reads page-numbered indexed text in bounded chunks and asks the configured DeepSeek model for JSON suggestions. It stores only suggestions whose exact source quote is present in the page text, whose quoted date agrees with the returned date, and whose confidence is between 0 and 1. Relative dates are resolved only for supported day-count phrases when an exact calendar-date base is also quoted in the same text chunk. Unsupported or unclear date expressions are skipped. Dates more than 30 days in the past are discarded. Provider and database failures use the durable job retry policy.

Suggestions remain `suggested` until the member confirms them. Each suggestion shows its exact source excerpt, page (when available), confidence, and the instruction “Check this date against the original document.” This is an aid for review, not a legal determination. The selected document shows its Important dates panel; Upcoming dates in the workspace lists active suggestions and confirmed items across the account. Members can edit and confirm, dismiss, mark a confirmed date done, snooze a pending reminder, and export an individual event as an `.ics` calendar file.

Confirming an event creates in-app reminders and email reminders for enabled channels at the configured lead times (defaults: 14, 7, and 1 days). Dates whose reminder times have already passed are not scheduled retroactively. Dismissed and completed dates cancel pending reminders. The preference record supports enabled channels, lead days, quiet-hour start/end, and an IANA timezone; the default timezone is `Africa/Nairobi`. Quiet-hour delivery is moved to the next quiet-hour end in that timezone. WhatsApp and SMS are not enabled yet; the `NotificationChannel` protocol leaves a clean adapter point for them.

The worker takes a PostgreSQL advisory transaction lock to enqueue at most one `send_due_reminders` job per UTC minute. Reminder rows are selected with `FOR UPDATE SKIP LOCKED`, then marked sent or failed. Failed deliveries are retried with exponential delay. In-app reminders are stored and visible in the Upcoming dates page. Email uses the SMTP adapter and these backend-only environment variables:

| Variable | Purpose |
| --- | --- |
| `SMTP_HOST` | SMTP server hostname; required for email delivery |
| `SMTP_PORT` | SMTP port; defaults to `587` |
| `SMTP_USER` | SMTP username; optional if the server permits unauthenticated delivery |
| `SMTP_PASSWORD` | SMTP password; never expose in browser variables |
| `SMTP_FROM` | Sender address; defaults to `SMTP_USER` |
| `SMTP_STARTTLS` | Enable STARTTLS; defaults to `true` |

Apply Alembic migrations `0014` and `0015` before deploying the updated API and worker. Migration `0014` creates `document_events`, `reminders`, and `notification_preferences`; `0015` repairs missing legacy conversation columns and indexes chat history. The endpoints are `GET /documents/{document_id}/events`, `GET /events/upcoming`, `POST /events/{id}/confirm`, `/dismiss`, `/done`, and `/snooze`, `POST /reminders/{id}/snooze`, `GET /events/{id}/ics`, `GET /notifications`, and `GET/PUT /notification-preferences`. All event and reminder reads and changes are scoped to the authenticated owner. No event is confirmed and no reminder is created by extraction alone.

The workspace loads chat history when a folder is expanded instead of blocking initial startup on that optional request. The history endpoint returns the latest 200 chats per account and uses a composite index. Upload limits are fetched only when the upload panel opens, removing that request from normal startup.

Email delivery uses an SMTP adapter with a stable per-reminder Message-ID and database row locking to prevent concurrent workers from delivering the same pending row. SMTP itself does not provide a universal exactly-once guarantee if a worker process is killed after the mail server accepts a message but before the database records success; deployment with a provider that supports idempotency keys can strengthen that crash-recovery boundary.

### Phase 2 release checklist

- [ ] Apply migrations `0014` and `0015` to the same production Postgres database used by the API and worker.
- [ ] Add SMTP settings to the Render backend/worker environment (never `VITE_*`), and verify email delivery with a controlled test account.
- [ ] Ensure the worker deployment uses the updated commit and shared `DATABASE_URL`; check it processes `extract_events` and recurring `send_due_reminders` jobs.
- [ ] Index a document with an explicit date, an anchored “N days after” obligation, a relative date without a base date, and unrelated dates. Verify only source-backed events appear with correct page excerpts.
- [ ] Confirm a suggestion and verify reminder rows use the preference timezone/lead times; dismiss another and verify no reminder is created.
- [ ] Test quiet hours across midnight, email failure retry, in-app reminder visibility, snooze, mark done, and `.ics` export.
- [ ] Review dates against their original document and do not present model suggestions as certain legal deadlines.

### Helpful support information (safe to share)

When reporting a problem, provide the deployment URL, approximate time, route/status code, non-secret error message, and relevant Vercel log lines. Do not send passwords, JWTs, `.env` files, API keys, consumer secrets, passkeys, or the administrator bootstrap code.


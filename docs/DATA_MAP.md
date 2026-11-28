# DocuMind AI data map

This engineering inventory is based on the SQLAlchemy models and migrations in this repository as of 28 November 2026. It is not a legal determination of personal data, lawful basis, controller/processor roles, or required retention. Provider regions and their own retention periods must be checked against current contracts and account settings.

## Account, content, and access tables

| Table | Data held | Purpose and deletion behavior |
|---|---|---|
| `users` | Name, email, password hash or linked-login state, verification/admin flags, language preference, TOTP secret | Account and access. Deleted by account deletion after dependent content cleanup. |
| `privacy_consents` | User reference, notice type/version, acceptance time | Evidence of notice acceptance; user reference becomes null on account deletion. Retention period needs operator/legal decision. |
| `knowledge_bases` | Folder name/description, personal owner or organization, sensitive flag | User document workspace. Personal folders cascade with account deletion; organization folders remain with the organization. |
| `documents` | Filename, MIME type, byte count, processing status/errors, uploader reference, storage identifiers/URL | Upload/index lifecycle. Original is stored in Cloudinary; rows and vectors are removed on deletion/retention. |
| `document_chunks` | Extracted document passages, page, embedding vector | Search and chat retrieval. Cascades with its document. |
| `conversations` | Owner, folder/document/library scope, title, visibility, timestamps | Chat history. Private chats are personal; shared chats belong to the organization workspace. |
| `messages` | User/assistant text, sources, metadata, timestamps, model name, optional actor reference | Chat transcript and citations. Cascades with conversation. |
| `answer_feedback` | Question, answer, cited sources, model version, rating, optional report/review note and user | Quality and safety review. Account deletion cascades its feedback. |
| `document_events` | Extracted dates/obligations, source excerpts, confidence, status, user and organization | User reminders and event review. Follows related data cleanup. |
| `reminders` | Event, user, channel, schedule, delivery status and error | Reminder delivery. Cascades with the event/user according to schema. |
| `notification_preferences` | User channels, lead times, quiet hours, timezone | Reminder delivery preferences. Removed with the account. |

## Organization and financial records

| Table | Data held | Purpose and deletion behavior |
|---|---|---|
| `organizations` | Name, type, creator, retention setting | Shared workspace. Owner-requested organization deletion removes organization-owned content. |
| `organization_members` | Organization, user, role, join time | Access control; cascades when membership/account/organization is deleted. |
| `organization_invites` | Invite email, role, token hash, expiry, inviter | Access invitation. Organization deletion removes invites; inviter is nulled on account deletion. |
| `subscriptions` | User or organization plan, status, dates and seat limit | Access and billing. Cascade behavior follows user/organization. Confirm any statutory financial retention before deletion policy is finalized. |
| `mpesa_payments` | Payer phone, amount, status, receipt and Daraja request identifiers | Payment processing and reconciliation. Current schema cascades with account/subscription; confirm required financial record retention before enabling account erasure in production. |
| `payment_recovery_requests` | Phone, paid time, submitted M-Pesa message, review and decision details | Manual payment recovery. Current schema cascades with account; confirm retention needs before production. |
| `subscription_plans` | Public plan definitions and prices | Billing catalogue; not user-specific. |

## Background operations, audits, and data rights

| Table | Data held | Purpose and deletion behavior |
|---|---|---|
| `jobs` | Job type, JSON payload (may include user/document IDs), status, errors and retry data | Background processing. Job payload/error retention is operational and needs a cleanup schedule. |
| `audit_events` | Actor/resource UUIDs, organization UUID, action, details and timestamp | Append-only audit trail. Intentionally survives deletion; UUIDs and existing details can remain identifying. Minimize fields and agree retention with counsel. |
| `admin_audit_logs` | Admin/recovery UUIDs, action, reason/details and time | Append-only platform-admin trail. Raw UUIDs remain after deletion. Do not put unnecessary names, emails, or payment-message text here. |
| `security_counters` | HMAC-derived rate-limit bucket, counts, lock times | Abuse prevention. Bucket is not plaintext email/IP but can be correlatable; implement periodic expiry/cleanup. |
| `data_export_requests` | Owner/requester UUID, organization, status, error and Cloudinary asset ID | Tracks privacy exports. Archive expires after seven days; metadata needs a defined retention policy. |
| `data_deletion_requests` | Target and requester UUIDs, status, errors and timestamps | Tracks queued erasure. Retained as operational/audit evidence; decide retention period. |

## Shared library and communications

| Table | Data held | Purpose and deletion behavior |
|---|---|---|
| `library_collections`, `library_documents`, `library_chunks`, `library_updates` | Official/public document catalogue, text, vectors, version hashes and update events | Shared read-only library. Not user-uploaded personal data, but ingestion logs and source metadata still need governance. |
| `whatsapp_links` | User reference, phone, consent/opt-out and last scope | Link a WhatsApp number and honor opt-out; cascades with account. |
| `whatsapp_link_challenges` | User, phone, one-time-code hash, expiry and attempts | Verify channel linking; cascades with account; expire promptly. |
| `whatsapp_messages` | Phone, provider IDs, inbound/outbound message text, media IDs and provider payload | WhatsApp handling and idempotency. Account deletion behavior follows FK; unlinked-number messages may have no user ID, so require a separate retention/cleanup policy. |
| `whatsapp_consent_events` | Phone, action, source, provider message ID, optional user | Evidence of opt-in/opt-out; retained separately, review retention and minimization. |
| `message_usage` | User reference, message ID, provider ID, unit/cost/currency/status | Channel cost accounting. User reference becomes null on deletion; billing retention needs review. |
| `whatsapp_document_uploads` | Document, inbound message, user, notification time | Connects incoming media to indexing and ready notifications; cascades with related account/document. |

## External processing described by the app

- DeepSeek: receives questions, retrieved passages, and requested translations for answer generation.
- Cloudinary: stores uploaded originals and temporary authenticated export archives.
- Neon/PostgreSQL: account, content, vectors, chats, billing, and operational data.
- Vercel: web frontend and API routing; Render: API and long-lived background worker.
- Bird: WhatsApp content, phone numbers, media, and notifications when enabled.
- Safaricom Daraja: M-Pesa prompts and callbacks, including phone and transaction identifiers.

The app does not currently know or assert provider data-center locations, transfer safeguards, subprocessors, or contractual deletion periods. Populate the operator identity and ODPC registration details only after confirming them; placeholders in the app are intentional.

## Known gaps to resolve before making privacy commitments

1. Define TTL cleanup for jobs, rate-limit buckets, export/deletion request rows, consent evidence, WhatsApp messages/consent events, and audit logs.
2. Review M-Pesa and recovery records: current user deletion cascades them, while applicable accounting/consumer obligations may require a different design.
3. Audit existing organization activity details for names/emails and minimize them prospectively; immutable historical details cannot be edited without changing the audit guarantee.
4. Decide treatment of shared organization conversations and private member conversations in organization exports with the organization contract and legal adviser.
5. Verify deletion completion across database, Cloudinary, provider logs/backups, and any backups under provider retention windows; database deletion cannot itself erase provider backups.

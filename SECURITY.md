# Security and privacy operations

This file describes implemented controls and operator responsibilities. It is not a penetration-test report, compliance certificate, or legal advice.

## Authentication and browser sessions

- Browser sessions use the `documind_session` HttpOnly cookie. In production it must be Secure and SameSite=Lax. Set `AUTH_COOKIE_SECURE=false` only for local HTTP development.
- Unsafe browser requests require a matching `documind_csrf` cookie and `X-CSRF-Token` header. The M-Pesa and Bird webhook routes are exempt because they authenticate provider signatures instead.
- Rotate `JWT_SECRET_KEY` after suspected exposure. Keep OAuth client secrets, database credentials, Daraja keys, and provider keys in the backend runtime only.
- Login endpoints apply database-backed throttles and temporary lockout after repeated bad credentials. Admins can enroll a TOTP authenticator in Security settings. Keep recovery procedures private and verify administrator identity before resetting MFA.
- Consent is versioned by `TERMS_VERSION` and `PRIVACY_POLICY_VERSION`. Bump these values when approved notices change; users are asked to accept the new versions.

## Upload and AI boundaries

- Uploads are size-capped and checked against file signatures. DOCX ZIP entries are bounded and checked for suspicious expansion, path traversal, encryption, and macros. PDFs are parsed strictly and rejected for selected active-content features and excessive linked objects/pages. Images are dimension-capped during OCR.
- These checks reduce risk; they do not replace antivirus scanning or sandboxing. Keep worker libraries and OS packages patched, and consider malware scanning before accepting high-risk organizational documents.
- A folder marked sensitive displays a warning. **It does not prevent content being sent to the configured hosted AI provider.** Use only when authorized. `backend/app/services/ai_provider.py` is the adapter boundary for a future self-hosted or region-specific model.
- The worker runs separately from the web API. Restrict its database and Cloudinary credentials, monitor failed jobs, and do not execute document content.

## Data rights, audit, and retention

- Personal and organization exports are queued jobs. Download links are signed and short-lived; archive objects expire and are cleaned up by the worker.
- Account and organization deletion are queued and retry if Cloudinary cleanup fails. A failed cleanup must be investigated; do not manually mark the request complete while external files remain.
- Organization retention is optional and disabled by default. When configured, the daily worker removes organization documents and conversations older than the selected number of days.
- `audit_events` and `admin_audit_logs` are append-only at the database trigger layer. They retain raw identifier references after deletion. Review the payloads and retention rationale with counsel; never put passwords, tokens, document text, or receipt contents in audit details.
- See [docs/DATA_MAP.md](docs/DATA_MAP.md) for the table-by-table personal-data map and known gaps.

## Operational checklist

1. Set `AUTH_COOKIE_SECURE=true` in production and serve the app only over HTTPS.
2. Use separate least-privilege secrets per environment; rotate compromised credentials immediately.
3. Restrict database access to the API and worker. Require TLS and backups with tested restore procedures.
4. Configure provider contracts, data locations, subprocessors, and retention from current provider settings; the app cannot infer these facts.
5. Alert on repeated login failures, job failures, unusual exports/deletions, and webhook signature errors.
6. Keep a human incident process for containment, evidence preservation, affected-user assessment, and any required notifications. Confirm notification duties and deadlines with a qualified Kenyan adviser.
7. Before production rollout, apply migrations in a reviewed maintenance window and verify rollback/backup plans. This change has not been applied to production by this implementation.

## Responsible disclosure

Report suspected vulnerabilities privately to the platform operator using a contact address the operator supplies. Do not include live secrets or another person's documents in a report. Add the operator's security contact before public launch.

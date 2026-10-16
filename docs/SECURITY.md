# Security controls and operating limits

Updated 15 October 2026 after the local security audit. This remains a single-tenant, synthetic-data pilot. The changes below are not a security certification or a verified public deployment.

## Access

Every authenticated write is administrator-only unless the resolved route has an explicit operator/reviewer permission. Vendor aliases and manual watcher triggers require admin. Signed-in users still share one workspace: invite only trusted pilot participants.

Self-signup is off by default and forced off in Compose. Where explicitly enabled locally, registration creates a **disabled operator account** and returns no session. An administrator must enable it on Accounts before the user can sign in or read workspace data. Existing enabled accounts are unchanged. Verify the person's identity and intended workspace access before enabling a request. The security log records `signup_requested` and subsequent enable events.

Passwords use salted scrypt; missing accounts receive equivalent hash work. Failed attempts no longer set a victim-wide 15-minute lock. Instead, login is throttled to a 30-request burst per actual backend peer, replenishing over 60 seconds, with a 120-request global bucket. Signup has a five-request per-peer bucket. Forwarded address headers are not trusted. Behind the frontend proxy, users can share a peer bucket; keep this conservative pilot limit and deploy a trusted edge rate limiter before a public service. These process-local controls assume one backend worker and reset on restart.

Successful login is limited to five active sessions per account; disabling an account or resetting its password revokes sessions. Authentication events are retained up to 10,000 rows. No passwords/tokens are written to the event log.

## Requests and resources

- Frontend and backend both count actual incoming bytes, including chunked requests: 256 KiB for JSON/other writes, 11 MiB for multipart requests. The body-read deadline is 15 seconds, with at most eight active writes per process.
- Source files remain limited to 5 MiB and contract PDFs to 10 MiB. Caddy enforces an additional 11 MB gateway limit.
- A signed-in user receives a 60-write/minute token bucket and a 20-assessment/hour bucket on intake, corrections, investigations, and defense. Inference runs at most two requests concurrently and rejects excess work rather than building an unbounded waiting queue. These controls are not a billing guarantee.
- Pilot storage is capped at 1,000 cases, 1,000 contracts, 200 accounts, 10 sources/case, and 256 MiB of document payloads. Reviews and corrections are capped at 100 each per case. Limits fail explicitly instead of deleting records. Backups and database overhead are outside the document-payload quota.
- Case and contract list endpoints default to 100 rows and accept `limit` up to 200 and nonnegative `offset`. The current UI shows the initial page; use the API to inspect additional pages.
- PDF parsing runs in a short-lived subprocess with a 12-second deadline, at most two workers, 50 pages, bounded decompression, and 400,000 extracted characters. Linux workers additionally have CPU/address-space limits. Windows uses subprocess/time/format limits but no OS memory sandbox; do not treat this as malware isolation.

## Data validation

Contract/incident schemas reject non-finite numbers and bound monetary values, SLA intervals, list sizes and text lengths. The exact serialized contract is validated before storage. Recognized synthetic sources are type-checked before insertion; invalid historical source records produce a visible finding and block approval instead of crashing the source list. Generic attachments still require human inspection and are not authenticated or antivirus-scanned.

No existing user records are silently repaired or deleted. If an old database contains an invalid contract, preserve a backup and inspect that record before correcting it. The security audit's poisoned records were disposable and never entered the user's live database.

## Hosted configuration

Use `.env.deploy.production.example`. It sets `INFRACLAIM_DEPLOYMENT=hosted` and `AUTH_COOKIE_SECURE=true`; hosted startup rejects disabled authentication or insecure cookies. Keep the backend private. Caddy supplies HTTPS and HSTS when configured for a real hostname. Verify cookie flags, redirects, certificate, authentication and persistence at the actual deployed URL before sharing it.

The frontend supplies frame denial, nosniff, referrer/permissions policies and a restrictive-origin CSP. Inline scripts/styles remain allowed for compatibility with the current Next.js static build; the policy is not a nonce-based XSS guarantee. Origin checks reject cross-site and malformed browser write origins; non-browser callers still need sessions.

## Still outside this pilot

Multi-tenant isolation, MFA, distributed abuse controls, encrypted offsite backups, customer retention policy, malware scanning, independent penetration testing, container/base-image vulnerability assessment, and actual public TLS/edge verification remain deployment or production work. Prompt-injection tests use mock transports; live model robustness and source authenticity are not established by a passing local suite.

Run the backend regression suite, rebuild the frontend, replay the recorded HTTP security tests, then regenerate the submission ZIP after changes. Historical audit findings and evidence are retained separately from the remediation report.

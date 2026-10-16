# Phase 6 status — updated 2026-10-13

## Security remediation — 15 October 2026

The later security changes supersede the historical immediate-signup behavior below. New signup requests remain disabled until administrator approval. Admin checks cover alternate vendor routes and watcher triggers. Bounded input validation, safe source analysis, streamed body limits, throttles, pilot quotas, isolated PDF parsing, and hosted-cookie startup checks were added. See [SECURITY.md](SECURITY.md) for limits and residual risks. Fresh verification results are recorded separately in the security remediation report; historical test/live-model results below retain their original scope.

## Current demo usability and source-check update

The `pilot_manual_001` flow now offers one-click attachment of its three bundled synthetic files and a form button to fill the matching incident values before an audited correction. Structured synthetic ticket, telemetry, and maintenance exports are compared against the entered incident; mismatches appear beside the files and block approval. Generic files still require a separate human comparison. A sign-out control remains visible on narrow screens so operators can switch to the reviewer account. Backend suite: 94 passed with one upstream Starlette/httpx deprecation warning; frontend production build passed. The running local site returned the review page and source-check results after restart. The user's current case still has mismatched entered timestamps and remains in human review; no approval or vendor action was performed on their behalf.

## Latest internal pilot update

Admin account creation, disable/enable, password reset, session revocation, and a security-change log now work. Manual case approval requires ticket, telemetry, and maintenance source files with checksums and a distinct reviewer's recorded comparison. The file origin remains operator supplied; there is no trusted customer-system connection. A consistent SQLite backup was created on D: and restored to a separate verified copy. All 94 backend tests and the frontend production build pass.

One isolated **live-model manual-source smoke test** completed: one successful Nemotron Lightning assessment, a $40,000 synthetic proposed credit, three consistent synthetic source fixtures, and reviewer approval to `claim_ready`. No vendor claim or credit was sent or recovered. See [live manual-source report](../reports/PILOT_SOURCE_LIVE_SMOKE.json) and [data handling](DATA_HANDLING.md).

A separate **running-site rehearsal** then passed through the local website proxy: PDF ingest, a live Nemotron manual assessment, three uploaded and downloaded source files, named reviewer approval, simulated dispute/acceptance, and one matched simulated $40,000 memo. After restarting the backend, the case and source/PDF checksums persisted, and a repeated reconciliation left the summary unchanged. See [running-site report](../reports/PILOT_PROXY_REHEARSAL_LIVE.json) and [restart check](../reports/PILOT_RESTART_CHECK.json). No real vendor action or financial recovery occurred.

## Account update

Individual local accounts now protect the pilot. Operator, reviewer, and admin roles are enforced on writes. Reviews and corrections record the signed-in username even if a caller sends a different name. Sessions use revocable, 12-hour HTTP-only cookies; passwords are salted and hashed. Three generated local accounts are in `work/pilot-accounts.txt`, which is excluded from the release ZIP. Local sign-in, access, and sign-out passed through the browser-facing proxy. This is still a single-tenant synthetic pilot, not a real-customer deployment.

The local pilot now offers self sign-up. New sign-ups receive the operator role and a session immediately; they cannot approve reviews or manage accounts. The setting is explicitly enabled in the private local environment and remains disabled by default in release configuration. The sign-up page and browser-facing status endpoint were checked on the running site; automated tests cover account creation, duplicate names, role restriction, and disabled sign-up.

The merged local demo is running at `http://localhost:3000/`. The Nebius key is configured privately. No remote deployment or real financial recovery is claimed.

The application UI was redesigned across overview, intake, and review. A shared navigation system now leads from the case register to a two-step contract/incident intake and then to a human decision. Approval links back to the exact case for simulated submission. The accounts, review, and populated source panels were rendered after sign-in at 375px and 1440px with no horizontal overflow. See [interface direction](DESIGN.md).

## Completed and verified

- Merged the separate Phase 3 persistence and reconciliation backend with the extracted Phase 5 project that contained the Phase 4 dashboard. The original folders and databases remain untouched.
- Preserved persistent cases, idempotent vendor claims, counter-investigation, policy gates, simulated posted-credit matching, restart recovery and the ambiguous-case hold.
- Added secure backend environment configuration, structured Nemotron outputs, bounded requests, strict citation and policy checks, and per-call provenance.
- Repaired the local dashboard's stale build/style serving problem, revised its visual treatment and copy, and verified a rendered browser capture. The current HTML, stylesheet, API runtime and contract ingestion routes respond successfully.
- Added a cooling-SLA pilot intake page: checked contract terms can be saved and used with operator-entered incidents. Uploaded originals are now stored in SQLite and linked to the saved contract by checksum. Manual case records persist and are held for human review; entered evidence remains unverified.
- Added a review page and version-checked decisions: approve for simulated submission, reject, or request information. An unsubmitted manual incident can now be corrected and reassessed; prior values are retained in the case audit and a new human decision is required. Approval cannot override the existing evidence/model/policy gate. New decisions use signed-in account identities.
- The frontend production build passed. All 94 backend tests passed with one upstream Starlette/httpx deprecation warning. Pilot tests cover PDF/source linkage and retrieval, identity-backed approval, correction/reassessment, backup/restore, persistence, simulated submission, stale decisions and conflicting-evidence blocks.
- An isolated synthetic browser rehearsal uploaded and linked the PDF, then corrected a maintenance record. Mock reassessment changed the proposed credit from $36,666.67 to $40,000; the case stayed in human review with one recorded amendment and no vendor claim.
- The 50-case mock suite passed with 100% route and financial accuracy and no unsafe autonomous actions. Mock results do not measure model quality.
- The latest five-case **real-model smoke evaluation** completed five successful provider calls with 100% route and financial accuracy and no unsafe autonomous actions.
- The latest 50-case **real-model evaluation** completed 50 successful provider calls and valid assessments: 100% route accuracy, 100% financial exact match, zero unsafe autonomous actions, and 100% safety on human-review/close cases. A contradictory citation instruction was removed before this run. This is a bounded test result, not a guarantee for future cases.
- Three **live end-to-end rehearsals** passed, including one after the final citation prompt change. Each used real Nebius inference for the hero investigation, vendor dispute and ambiguous case; the $40,000 credit and vendor actions remained simulated. The posted credit matched after an API restart and duplicate reconciliation booked once.
- Docker images and password-protected local container deployment were previously validated, including workflow and restart persistence. No hosted deployment has been verified.
- Added a public-demo deployment guide and production Compose example. The production Compose configuration parses successfully; the server and domain have not been created.

## Remaining

1. For a public deployment, choose a host and domain, configure server-side secrets and HTTPS, then verify authentication, persistence and the full workflow at the deployed URL.
2. Continue monitoring live citation format and provider reliability beyond the 50-case suite. Unknown or prose citations still go to human review.
3. For a real customer pilot, connect at least one trusted ticket/telemetry/calendar system and real vendor/credit endpoints, approve customer-data retention and encrypted offsite backup policy, and validate against customer cases. The one-case live manual-source smoke and previous 50-case live evaluation used synthetic fixtures; they do not establish customer accuracy.

## Evidence

- [Latest live smoke](../reports/PHASE6_EVALUATION_LIVE_SMOKE_ROTATED_V3.json)
- [Latest full live evaluation](../reports/PHASE6_EVALUATION_LIVE_CITATION_FINAL.json)
- [Earlier full live evaluation](../reports/PHASE6_EVALUATION_LIVE_FINAL.json)
- [Live rehearsal 1](../reports/PHASE6_REHEARSAL_LIVE_UI_REFRESH.json)
- [Live rehearsal 2](../reports/PHASE6_REHEARSAL_LIVE_UI_REFRESH_REPEAT.json)
- [Live rehearsal after final change](../reports/PHASE6_REHEARSAL_LIVE_CITATION_FINAL.json)
- [Mock evaluation](../reports/PHASE6_EVALUATION_MOCK.json)
- Rendered dashboard (historical screenshot omitted)
- Pilot intake page (historical screenshot omitted)
- Review page (historical screenshot omitted)
- Redesigned overview (historical screenshot omitted)
- Redesigned intake (historical screenshot omitted)
- Redesigned review (historical screenshot omitted)
- 375px intake layout (historical screenshot omitted)
- [Public demo deployment guide](GO_LIVE.md)
- [Internal pilot runbook](INTERNAL_PILOT.md)
- [Internal pilot rehearsal result](../reports/INTERNAL_PILOT_QA.json)
- [Running-site live synthetic rehearsal](../reports/PILOT_PROXY_REHEARSAL_LIVE.json)
- [Restart persistence check](../reports/PILOT_RESTART_CHECK.json)
- Account page desktop (historical screenshot omitted)
- Review page mobile after sign-in (historical screenshot omitted)
- Populated source panel mobile (historical screenshot omitted)
- Populated source panel desktop (historical screenshot omitted)

All vendor calls and credit memos are simulated, even when inference is live. This is a single-tenant prototype, not a production financial enforcement system.

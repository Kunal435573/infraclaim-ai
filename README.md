# InfraClaim AI — Phase 6 and internal pilot

This public repository excludes private environment files, saved accounts, local databases, and generated passwords. Follow the setup instructions below to create a fresh local pilot.

**Security update — 15 October 2026:** vendor aliases now enforce admin permissions; signup requests require administrator approval; invalid numeric/source data is rejected; request/resource limits and hosted cookie safeguards are enabled. Read [security controls and limits](docs/SECURITY.md) before sharing the demo. This remains a trusted, single-workspace synthetic pilot.

An infrastructure contract-enforcement demo with persistent cases, evidence-grounded AI interpretation, deterministic financial controls, simulated vendor disputes and posted-credit reconciliation.

**Vendor actions and credits are simulated in every mode. Live mode means real Nebius inference, not real money recovered.**

## What was merged

The extracted Phase 5 project contained the Phase 4 dashboard and evaluation suite but lacked Phase 3's persistent workflow. This copy combines Phase 3's SQLite/backend/safety improvements with that dashboard and the corrected evaluations. Both originals remain untouched. File hashes and choices are in [docs/INTEGRATION.md](docs/INTEGRATION.md) and [docs/SOURCE_MANIFEST.json](docs/SOURCE_MANIFEST.json).

## Local start (Windows)

Requires Python 3.11 and Node.js 22 or newer.

```powershell
python run.py --setup
```

After setup, use `python run.py` or `START.cmd`. Dashboard: `http://localhost:3000`; API documentation: `http://localhost:8000/docs`. Local servers bind to loopback. For a hosted demo, use the protected deployment in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

On a fresh database, create local pilot accounts once before signing in:

```powershell
cd backend
.venv\Scripts\python.exe -m scripts.create_pilot_users ..\pilot-accounts.txt
```

Keep `pilot-accounts.txt` private and out of Git. It contains generated admin, operator, and reviewer passwords. Sign in through `/login`; permissions are enforced by the backend.

The dashboard includes the Phase 4 evidence graph, timeline, contract provenance, persistent exception queue, recorded policy checks, counter-investigation and reconciled recovery ledger. It restores saved cases and labels the inference mode and simulation clearly.

## Cooling-SLA pilot intake and review

Open `/intake` to upload a supported PDF or enter terms from a source clause, check the fields, and save the contract. Uploaded originals are stored in the local SQLite database, linked by checksum to the saved contract, and available for download in review. Manually entered terms have no archived PDF. Then enter an incident to create a persistent case. Operator-entered ticket, acknowledgement, telemetry and maintenance details are labelled as unverified. This pilot supports hourly credits with a planned-maintenance exclusion; it is not a general contract parser.

Every manually entered claim is held for review, even if the model and policy would otherwise support it. Open `/review` to inspect the clause, evidence, citations and calculation, then record approval for **simulated** submission, rejection or a request for more information. An operator can correct an unsubmitted manual incident in review; previous values remain in the case audit, the model and fixed rules reassess the case, and a new human decision is required. Approval cannot override missing evidence, unresolved contradictions, a failed model assessment or the policy gate. Reviews and corrections record the signed-in username. Operators can create and correct cases, reviewers can decide them, and admins can run simulated vendor actions. This is not a production approval system.

The operator can attach ticket, telemetry, and maintenance source files to a manual case. The files are stored with checksums. A separate reviewer must select all three types and record how they compared them with the entered incident before approval. The app does not authenticate file origin or parse these uploads into model evidence. Synthetic examples and the step-by-step rehearsal are in [docs/INTERNAL_PILOT.md](docs/INTERNAL_PILOT.md). Admins can create or disable accounts and reset passwords from `/accounts`.

The local SQLite database can be backed up consistently and restored to a new path with checksum and integrity verification. See [docs/DATA_HANDLING.md](docs/DATA_HANDLING.md). The current backup is unencrypted and is suitable only for this synthetic pilot.

## Live Token Factory configuration

Copy `backend/.env.example` to `backend/.env` only if that local file does not already exist. Set the following in the backend file or your server's secret environment:

```dotenv
NEBIUS_API_KEY=YOUR_PRIVATE_TOKEN_FACTORY_KEY
INFRACLAIM_LLM_MODE=live
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_LIGHTNING_MODEL=nvidia/Nemotron-3_5-Lightning
NEBIUS_SUPER_MODEL=nvidia/nemotron-3-super-120b-a12b
DATABASE_PATH=data/infraclaim-live.sqlite3
```

Do not put secrets in the frontend or chat. `.env` files are excluded from Git, container images and the release ZIP. Keep separate mock and live databases so old mock cases cannot masquerade as live cases. Switching runtime mode blocks actions on cases assessed in another mode.

The live evaluator checks the account's model catalog first; unavailable IDs are reported, never silently replaced. Routine investigations use Lightning; conflicting investigations and dispute defenses use Super. Requests use a strict JSON schema, bounded timeout/retries and no redirects. Invalid output, refusal, unknown citations, missing credentials or provider errors require human review. Money, timing, caps and action authority remain deterministic.

`GET /ai/runtime` reports configuration, not successful inference. `GET /ready` reports configuration readiness only. Each assessment records execution type, model request/response identifiers, schema/prompt hashes, latency, token usage where returned, and failures without provider bodies or secrets.

## Test, evaluate and rehearse

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
cd ..
backend\.venv\Scripts\python.exe scripts/evaluate.py --mode mock --count 50
backend\.venv\Scripts\python.exe scripts/evaluate.py --mode live --count 5
backend\.venv\Scripts\python.exe scripts/evaluate.py --mode live --count 50
backend\.venv\Scripts\python.exe scripts/rehearse.py --mode mock
backend\.venv\Scripts\python.exe scripts/rehearse.py --mode live
```

The evaluator never switches modes. Live preflight without credentials writes a **blocked report with zero scenarios and null metrics**, returning a nonzero exit code. Offline tests force mock configuration; HTTP fixtures are labelled `test_transport` and cannot qualify as real-model results.

The frozen 50-case suite covers eligible/capped claims, complete exclusion, partial overlap and wrong-vendor cases. Expected amounts are independently specified. Final guarded route accuracy is separate from the model's raw decision. The model receives deterministic context, so even live results measure **assisted decision accuracy**, not standalone financial reasoning or general production accuracy. Failures stay in denominators. A mock 100% score is not a Nemotron quality claim.

See [docs/DEMO.md](docs/DEMO.md) for the demo script, [docs/STATUS.md](docs/STATUS.md) for verified results and remaining work, and `reports/` for recorded evidence. The inherited `PHASE5_EVALUATION_MOCK.json` is historical, unverified evidence from the original package.

## Scope and limits

- This is a single-tenant pilot/demo; it has no real vendor, payment or customer-data integrations.
- PDF extraction supports the supplied template. A successfully parsed original is staged in SQLite and linked when the contract is saved; unlinked staging records older than 24 hours are purged on startup or the next upload/save. This local database contains PDFs and must be treated as sensitive customer data.
- SQLite transactions, idempotency and version checks preserve cases and prevent double booking. Run one backend process/replica with durable storage.
- Demo business time is fixed at 2026-10-07 for replayable fixtures. Manually entered cases use current UTC for claim-window checks; a full deadline service remains future work.
- Human review decisions, incident corrections, and account changes are persisted with signed-in usernames. Uploaded source files still depend on human comparison; trusted system integration, encrypted offsite backup, and an approved customer-data retention/deletion schedule remain future work.
- Model confidence is self-reported and uncalibrated. Deterministic checks independently control actions.

## API workflow

`POST /contracts/demo/ingest` → `POST /demo/investigate/inc_cooling_001` → `POST /cases/{id}/run-loop`.

The worker submits, simulates dispute, counter-investigates, simulates acceptance and matches a posted memo before recording recovery. Manual endpoints remain available: `/submit`, `/simulate-dispute`, `/defend`, `/simulate-accept`, `/reconcile`, `/step`. The deprecated `/accept-and-verify` only verifies after a matching posted memo exists.

`GET /cases`, `/cases/{id}`, `/cases/{id}/evidence-graph`, `/cases/{id}/claim-package`, `/recovery-summary` expose persisted results. `POST /demo/investigate/inc_cooling_ambiguous` demonstrates blocked action. The evaluation HTTP endpoint is disabled by default to avoid unbounded public inference spending; use the local command.

`POST /contracts/ingest` parses and stages a supported PDF. `POST /contracts` confirms terms and links the original; `GET /contracts` lists contracts and `GET /contracts/{id}/source` downloads a linked original. `POST /cases/intake` creates a manual case. `POST /cases/{id}/amend` corrects an unsubmitted manual case with a version check and reassessment. `POST /cases/{id}/review` records a version-checked human decision. These endpoints do not call a real vendor.

## Provider references checked for this integration

- [Nebius Token Factory quickstart](https://docs.tokenfactory.nebius.com/quickstart)
- [Structured output and JSON schema](https://docs.tokenfactory.nebius.com/ai-models-inference/json)
- [Nemotron lineup and API examples](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference)
- [Public serverless endpoint limitations](https://docs.tokenfactory.nebius.com/public-serverless)

Live compatibility with the user's account still requires the separate real-model run; documentation and mocked requests do not establish it.

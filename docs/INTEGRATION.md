# Phase 3 / 4 / 5 integration

Both original folders are preserved. Neither source is a Git repository. SHA-256 hashes and file-by-file selections are recorded in SOURCE_MANIFEST.json before Phase 6 edits.

## Verified differences and merge decisions

- Phase 5 has an in-memory CASES dictionary; it does not contain Phase 3 persistence, transactional vendor claims, autonomous workflow, or memo reconciliation.
- Phase 3 supplies the backend, all safety/regression tests, SQLite store, idempotency, optimistic concurrency, recovery ledger and watcher.
- Phase 5 supplies the Phase 4 dashboard layout, source graph, timeline and contract panels. Its action wiring must be adapted to Phase 3's persistent API, polling, exceptions and recovery totals.
- Phase 5 supplies the evaluation framework; its expected amounts currently call the implementation under test, and generated dates can exceed Phase 3's frozen clock. Correct both before benchmarking. Mock citations also reference nonexistent maintenance evidence in some cases.
- Preserve the newer Phase 3 frontend dependency pins/lockfile and build configuration rather than downgrading to Phase 5's older packages.
- The historical PHASE5_EVALUATION_MOCK.json is unverified prior evidence, not a result of this task. Phase 6 reports go in reports/ with explicit mode and provider-call provenance.
- Original runtime databases, secrets, environments and build caches are not imported. Phase 6 starts a fresh demo database; original cases remain in the original Phase 3 folder.

## Phase 6 work

Harden live inference, schema validation, evidence citations and failure handling; preserve deterministic financial authority; isolate mock/live evaluations and record actual request outcomes; prepare a protected single-instance deployment; rehearse the full synthetic workflow.

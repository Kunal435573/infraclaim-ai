# What InfraClaim does

InfraClaim helps infrastructure operators identify and recover service credits owed when a vendor misses a contractual service promise. The operator provides the governing contract and an incident. InfraClaim links the relevant clause to the incident timeline, calculates a proposed credit with fixed rules, assembles cited evidence, and presents a claim for human review. It then tracks vendor response and whether a matching credit was actually posted.

The first buyer would be an infrastructure or commercial-operations team that manages costly vendor SLAs. The useful outcome is a defensible claim and a verified credit record, not merely an AI summary of a contract.

## Current product slice

- An internal cooling-SLA pilot supports contract-term confirmation, archived uploaded PDFs, operator-entered incidents, saved cases, incident corrections, evidence review and recorded human decisions.
- Nebius Nemotron assists with interpreting the supplied records. Deterministic code controls amounts, exclusions, deadlines and action authority.
- The public demo can be password protected. Individual reviewer identities are not yet authenticated.
- Vendor submission, disputes, acceptance and posted credits are simulated. No real money has been recovered.

## What remains before a real customer pilot

1. Archive original incident source files and verify operator-entered corrections against those records. Define retention and backup rules for stored PDFs.
2. Add individual accounts and roles that tie decisions to authenticated people.
3. Connect one real incident/ticket source, one vendor claim channel and one credit ledger. Validate the workflow with that vendor's actual contract terms.
4. Expand contract coverage only when each new clause type has a reviewed calculation rule and test cases.

The local demo and 50-case live evaluation establish that the current synthetic workflow can run; they do not prove customer-contract accuracy or real credit recovery.

# InfraClaim delivery plan

The hackathon plan has six phases. A phase number does not prove all preceding work was merged or tested.

1. Foundation: synthetic incidents, contract model and deterministic entitlement.
2. Evidence: supported-template PDF ingestion, provenance, evidence graph and claim package.
3. Persistent workflow: vendor simulator, disputes, counter-investigation, action policy, SQLite cases, restart recovery and memo reconciliation.
4. Dashboard: operations layout, evidence graph, timeline, contract panels and exception queue.
5. Evaluation: 50 reproducible scenarios with explicitly labelled execution mode.
6. Integration and validation: safely merge all sources, harden Token Factory inference, run separate live evaluation, prepare protected deployment and rehearse.

Phase 6 implementation is in this merged folder. Synthetic cases have passed separate mock and live Nemotron evaluations, and the internal pilot has been rehearsed through the local website. Remote deployment remains incomplete until a host/domain is selected and verified. See docs/STATUS.md for measured results and their limits.

The internal pilot now has local authentication, role controls, human-review resolution, and a tested backup/restore path. Production work still includes tenant isolation, trusted source and real vendor integrations, a customer-approved data retention and encrypted backup plan, database migrations, job queues, observability, and customer validation. These are not part of the synthetic demo's completion claim.

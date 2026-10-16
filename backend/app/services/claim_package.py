from datetime import datetime, timezone
from app.schemas import ClaimChronologyItem, ClaimCase, ClaimPackage, InfrastructureIncident, VendorContract


def build_claim_package(case: ClaimCase, contract: VendorContract, incident: InfrastructureIncident, min_confidence: float = 0.90) -> ClaimPackage:
    chronology = [
        ClaimChronologyItem(at=incident.start, label="Infrastructure incident began", source_id="ev_telemetry"),
        ClaimChronologyItem(at=incident.ticket_opened_at, label="Operations ticket opened", source_id="ev_ticket"),
        ClaimChronologyItem(at=incident.vendor_acknowledged_at, label="Vendor acknowledgement received", source_id="ev_ack"),
        ClaimChronologyItem(at=incident.end, label="Infrastructure incident ended", source_id="ev_telemetry"),
    ]
    chronology.sort(key=lambda x: x.at)

    factual_basis = (
        f"{contract.customer} observed a {incident.severity} event affecting {incident.service} from "
        f"{incident.start.isoformat()} through {incident.end.isoformat()}. The incident is governed by "
        f"{contract.sla.source_section or contract.sla.id}. InfraClaim correlated contemporaneous telemetry, "
        "ticket timestamps, vendor acknowledgement records, and maintenance records."
    )
    requested_remedy = (
        f"Apply a contractual credit of ${case.amount_usd:,.2f} in accordance with {contract.sla.id}, "
        "subject to the governing agreement and the attached evidence package."
    )

    return ClaimPackage(
        case_id=case.id,
        claimant=contract.customer,
        respondent=contract.vendor,
        contract_id=contract.id,
        incident_id=incident.id,
        amount_usd=case.amount_usd,
        clause_ids=[contract.sla.id],
        chronology=chronology,
        evidence_ids=[e.id for e in case.evidence],
        factual_basis=factual_basis,
        requested_remedy=requested_remedy,
        generated_at=datetime.now(timezone.utc),
        approval_required=case.confidence < min_confidence,
    )

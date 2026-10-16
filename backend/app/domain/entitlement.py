from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from app.schemas import EntitlementResult, InfrastructureIncident, VendorContract


def _overlap_seconds(a_start, a_end, b_start, b_end) -> float:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(0.0, (end - start).total_seconds())


def calculate_entitlement(contract: VendorContract, incident: InfrastructureIncident) -> EntitlementResult:
    """Deterministic money/eligibility engine. No LLM arithmetic is allowed here."""
    reasons: list[str] = []
    if incident.vendor != contract.vendor or incident.service != contract.sla.service:
        return EntitlementResult(
            eligible=False,
            eligible_hours=0,
            gross_amount_usd=0,
            capped_amount_usd=0,
            exclusion_applies=False,
            reasons=["Incident vendor/service does not match the governing contract."],
        )

    incident_seconds = max(0.0, (incident.end - incident.start).total_seconds())
    intervals = sorted((max(incident.start, w.start), min(incident.end, w.end))
                       for w in incident.maintenance_windows if w.end > incident.start and w.start < incident.end)
    merged = []
    for start, end in intervals:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    excluded_seconds = sum((end - start).total_seconds() for start, end in merged)

    eligible_seconds = max(0.0, incident_seconds - excluded_seconds)
    eligible_hours = round(eligible_seconds / 3600, 4)

    if excluded_seconds > 0:
        reasons.append("Planned maintenance overlaps part of the incident and is excluded.")
    else:
        reasons.append("No planned-maintenance window overlaps the incident.")

    response_delay = incident.vendor_acknowledged_at - incident.ticket_opened_at
    if contract.sla.response_minutes is not None:
        if response_delay > timedelta(minutes=contract.sla.response_minutes):
            reasons.append("Vendor response-time SLA was breached.")
        else:
            reasons.append("Vendor response-time SLA was met.")

    eligible = eligible_hours > 0
    gross = float((Decimal(str(eligible_seconds)) / Decimal(3600) * Decimal(str(contract.sla.rate_per_eligible_hour_usd))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if eligible else 0.0
    capped = min(gross, contract.sla.cap_usd)

    return EntitlementResult(
        eligible=eligible,
        eligible_hours=eligible_hours,
        gross_amount_usd=gross,
        capped_amount_usd=round(capped, 2),
        exclusion_applies=excluded_seconds > 0,
        exclusion_reason="planned maintenance overlap" if excluded_seconds > 0 else None,
        reasons=reasons,
    )

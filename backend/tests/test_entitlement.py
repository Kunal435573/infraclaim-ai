from app.domain.entitlement import calculate_entitlement
from app.services.repository import load_contract, load_incidents


def test_primary_incident_is_40000_recovery():
    contract = load_contract()
    incident = load_incidents()[0]
    result = calculate_entitlement(contract, incident)
    assert result.eligible is True
    assert result.exclusion_applies is False
    assert result.eligible_hours == 4.0
    assert result.capped_amount_usd == 40000.0


def test_overlap_is_removed_deterministically():
    contract = load_contract()
    incident = load_incidents()[1]
    result = calculate_entitlement(contract, incident)
    assert result.exclusion_applies is True
    assert 0 < result.eligible_hours < 1

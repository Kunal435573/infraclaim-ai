from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.domain.entitlement import calculate_entitlement
from app.services.evidence_graph import find_contradictions


def cents(amount):
    return int((Decimal(str(amount)) * 100).quantize(Decimal('1')))


class AutonomyPolicy:
    def __init__(self, settings):
        self.settings = settings

    def evaluate(self, case, action, assessment=None):
        reasons = []
        contract, incident = case.contract_snapshot, case.incident_snapshot
        reasoning = assessment or case.reasoning
        business_now = datetime.now(timezone.utc) if case.source == 'manual' else self.settings.demo_now
        if not contract or not incident:
            reasons.append('Source snapshots are missing.')
        else:
            entitlement = calculate_entitlement(contract, incident)
            if not entitlement.eligible or cents(entitlement.capped_amount_usd) != cents(case.amount_usd):
                reasons.append('Amount or eligibility does not match deterministic entitlement.')
            if find_contradictions(incident):
                reasons.append('Contradictory evidence requires human review.')
            if incident.start < contract.effective_date:
                reasons.append('Incident predates the contract.')
            if action == 'submit' and business_now > incident.end + timedelta(days=contract.sla.claim_window_days):
                reasons.append('Contractual claim submission window has expired.')
            if business_now < incident.end:
                reasons.append('Incident has not ended at the configured business clock.')
        if case.source == 'manual' and action in {'submit', 'defend', 'accept'} and not case.review_approved:
            reasons.append('Manual cases require a recorded human approval before simulated vendor action.')
        if not reasoning or reasoning.decision != 'supported':
            reasons.append('Reasoning does not support autonomous action.')
        if reasoning:
            trace = reasoning.inference or {}
            if self.settings.infraclaim_llm_mode == 'live' and (trace.get('execution') != 'live' or trace.get('status') != 'succeeded'):
                reasons.append('Live mode requires a successful real provider assessment for this action.')
            if trace.get('requested_mode', self.settings.infraclaim_llm_mode) != self.settings.infraclaim_llm_mode:
                reasons.append('Case inference mode differs from the active runtime; start a fresh demo database.')
            if reasoning.confidence < self.settings.autonomy_min_confidence:
                reasons.append('Reasoning confidence below autonomous-action threshold.')
            if reasoning.contradictions:
                reasons.append('Reasoning reports unresolved contradictions.')
            allowed = {e.id for e in case.evidence}
            if contract:
                allowed.add(contract.sla.id)
            if not reasoning.citations or not set(reasoning.citations).issubset(allowed):
                reasons.append('Reasoning has missing or unknown evidence citations.')
            if contract and not {contract.sla.id, 'ev_telemetry'}.issubset(set(reasoning.citations)):
                reasons.append('Reasoning must cite both the governing SLA and incident telemetry.')
            maintenance_ids = {e.id for e in case.evidence if e.type in {'maintenance', 'maintenance_check'}}
            if not maintenance_ids.issubset(set(reasoning.citations)):
                reasons.append('Reasoning must cite all supplied maintenance records.')
        if case.amount_usd <= 0 or case.amount_usd > self.settings.autonomy_max_amount_usd:
            reasons.append('Amount is outside the autonomous authority limit.')
        package = case.claim_package
        if action in {'submit', 'defend', 'accept'}:
            if not package or package.approval_required:
                reasons.append('An approved claim package is required.')
            elif (cents(package.amount_usd) != cents(case.amount_usd)
                  or package.case_id != case.id or package.contract_id != case.contract_id
                  or package.incident_id != case.incident_id
                  or not contract or package.respondent != contract.vendor
                  or package.claimant != contract.customer
                  or package.clause_ids != [contract.sla.id]
                  or set(package.evidence_ids) != {e.id for e in case.evidence}):
                reasons.append('Claim package does not match its source case.')
        return {'action': action, 'allowed': not reasons, 'reasons': reasons,
                'at': datetime.now(timezone.utc).isoformat(),
                'business_time': business_now.isoformat(),
                'min_confidence': self.settings.autonomy_min_confidence,
                'max_amount_usd': self.settings.autonomy_max_amount_usd}

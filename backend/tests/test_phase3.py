import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.schemas import CaseState
from app.services.case_engine import CaseEngine
from app.services.nebius import NebiusClient, assess
from app.services.policy import AutonomyPolicy
from app.services.repository import load_contract, load_incidents
from app.services.store import Store, Conflict
from app.services.workflow import Workflow


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, auth_enabled=False, database_path=str(tmp_path / 'claims.db'),
                    watcher_enabled=False, credit_delay_seconds=0, infraclaim_llm_mode='mock')


@pytest.fixture
async def flow(settings):
    engine = CaseEngine(settings=settings)
    store = Store(settings.database_path)
    case = await engine.investigate(load_contract(), load_incidents()[0])
    store.create(case)
    return Workflow(store, engine, settings), case.id


async def accepted(flow):
    workflow, case_id = flow
    workflow.submit(case_id)
    workflow.dispute(case_id)
    await workflow.defend(case_id)
    return workflow.accept(case_id)


async def test_persist_restart_and_idempotent_recovery(flow, settings):
    workflow, case_id = flow
    await accepted(flow)
    assert workflow.store.summary()['verified_amount_usd'] == 0
    restarted = Workflow(Store(settings.database_path), CaseEngine(settings=settings), settings)
    case = restarted.reconcile(case_id)
    assert case.state == CaseState.VERIFIED
    assert case.amount_usd == 40000
    assert case.counter_investigation.citations
    assert restarted.reconcile(case_id).version == case.version
    assert restarted.store.summary() == {'verified_amount_usd': 40000, 'verified_cases': 1, 'currency': 'USD'}


async def test_duplicate_and_concurrent_submission(flow):
    workflow, case_id = flow
    with ThreadPoolExecutor(max_workers=6) as pool:
        submitted = list(pool.map(workflow.submit, [case_id] * 6))
    assert len({c.vendor_claim_id for c in submitted}) == 1
    with workflow.store.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM vendor_claims').fetchone()[0] == 1
    assert sum(e.state == CaseState.SUBMITTED for e in workflow.store.get(case_id).timeline) == 1


async def test_delayed_memo_never_books_early(flow):
    workflow, case_id = flow
    workflow.settings.credit_delay_seconds = 3600
    await accepted(flow)
    assert workflow.reconcile(case_id).state == CaseState.ACCEPTED
    assert workflow.store.summary()['verified_cases'] == 0
    assert workflow.store.memo(workflow.store.get(case_id).vendor_claim_id) is None


@pytest.mark.parametrize('field,value', [
    ('amount_cents', 1), ('currency', 'EUR'), ('claim_id', 'other'),
    ('case_id', 'other'), ('contract_id', 'other'), ('incident_id', 'other'),
    ('vendor', 'other'), ('customer', 'other'), ('status', 'pending'),
])
async def test_credit_mismatch_goes_to_review(flow, field, value):
    workflow, case_id = flow
    case = await accepted(flow)
    with workflow.store.transaction() as db:
        vendor = workflow.store.vendor(case.vendor_claim_id, db)
        memo = workflow.vendor.poll_memo(vendor, db)
        memo[field] = value
        db.execute('UPDATE credit_memos SET payload=? WHERE id=?', (json.dumps(memo), memo['id']))
    result = workflow.reconcile(case_id)
    assert result.state == CaseState.HUMAN_REVIEW
    assert field in result.reconciliation['mismatches']
    assert workflow.store.summary()['verified_amount_usd'] == 0


async def test_worker_resumes_mid_dispute_after_restart(flow, settings):
    workflow, case_id = flow
    workflow.enable_auto(case_id)
    await workflow.tick()
    await workflow.tick()
    assert workflow.store.get(case_id).state == CaseState.DISPUTED
    restarted = Workflow(Store(settings.database_path), CaseEngine(settings=settings), settings)
    for _ in range(3):
        await restarted.tick()
    case = restarted.store.get(case_id)
    assert case.state == CaseState.VERIFIED
    assert not case.auto_run


async def test_human_review_cannot_be_bypassed(flow):
    workflow, _ = flow
    case = workflow.store.create(await workflow.engine.investigate(load_contract(), load_incidents()[1]))
    assert workflow.enable_auto(case.id).state == CaseState.HUMAN_REVIEW
    for action in [workflow.submit, workflow.dispute, workflow.accept, workflow.reconcile]:
        with pytest.raises(Conflict):
            action(case.id)
    with pytest.raises(Conflict):
        await workflow.defend(case.id)
    assert (await workflow.step(case.id)).state == CaseState.HUMAN_REVIEW
    assert workflow.store.summary()['verified_cases'] == 0


@pytest.mark.parametrize('mutation', ['amount', 'package', 'confidence', 'decision', 'citations', 'contradiction', 'expired', 'limit'])
async def test_policy_rechecks_before_submission(flow, mutation):
    workflow, case_id = flow
    with workflow.store.transaction() as db:
        case = workflow.store.get(case_id, db)
        if mutation == 'amount': case.amount_usd = 49999
        if mutation == 'package': case.claim_package.respondent = 'Wrong vendor'
        if mutation == 'confidence': case.reasoning.confidence = 0.89
        if mutation == 'decision': case.reasoning.decision = 'needs_review'
        if mutation == 'citations': case.reasoning.citations = ['invented']
        if mutation == 'contradiction': case.reasoning.contradictions = ['unresolved']
        if mutation == 'expired': workflow.settings.demo_now += timedelta(days=60)
        if mutation == 'limit': workflow.settings.autonomy_max_amount_usd = 39999
        workflow.store.save(case, db)
    case = workflow.submit(case_id)
    assert case.state == CaseState.HUMAN_REVIEW
    assert case.vendor_claim_id is None
    assert not case.policy_decisions[-1]['allowed']


class BadReasoner:
    live = True
    def __init__(self, value): self.value = value
    async def reason_json(self, **kwargs): return self.value


@pytest.mark.parametrize('value', [
    {}, {'decision': 'supported', 'confidence': 2, 'summary': 'wrong'},
    {'decision': 'needs_review', 'confidence': 1, 'summary': 'unsupported', 'citations': ['ev_telemetry']},
    {'decision': 'supported', 'confidence': 1, 'summary': 'invented', 'citations': ['made_up']},
    {'decision': 'supported', 'confidence': 1, 'summary': 'missing maintenance', 'citations': ['ev_telemetry']},
])
async def test_counter_investigation_fails_closed(flow, value):
    workflow, case_id = flow
    workflow.submit(case_id)
    workflow.dispute(case_id)
    workflow.engine.nebius = BadReasoner(value)
    case = await workflow.defend(case_id)
    assert case.state == CaseState.HUMAN_REVIEW
    assert workflow.store.vendor(case.vendor_claim_id)['status'] == 'disputed'


async def test_stale_counter_investigation_is_rejected(flow):
    workflow, case_id = flow
    workflow.submit(case_id)
    workflow.dispute(case_id)
    delegate = workflow.engine.nebius
    class RacingReasoner:
        live = False
        async def reason_json(self, **kwargs):
            workflow.enable_auto(case_id)
            return await delegate.reason_json(**kwargs)
    workflow.engine.nebius = RacingReasoner()
    with pytest.raises(Conflict):
        await workflow.defend(case_id)
    assert workflow.store.get(case_id).state == CaseState.DISPUTED


async def test_live_missing_credentials_never_falls_back(settings):
    settings.infraclaim_llm_mode = 'live'
    settings.nebius_api_key = None
    case = await CaseEngine(settings=settings).investigate(load_contract(), load_incidents()[0])
    assert case.state == CaseState.HUMAN_REVIEW
    assert case.confidence == 0


async def test_live_http_request_and_schema(settings):
    settings.infraclaim_llm_mode = 'live'
    settings.nebius_api_key = 'test-key'
    def handler(request):
        assert request.url.path == '/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer test-key'
        body = json.loads(request.content)
        assert body['model'] == settings.nebius_super_model
        assert body['response_format']['type'] == 'json_schema'
        assert body['response_format']['json_schema']['strict'] is True
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
            'decision': 'supported', 'confidence': 0.98, 'summary': 'Evidence supports defense.',
            'citations': ['ev_telemetry', 'ev_maintenance_0', 'sla.cooling.7.4'],
            'contradictions': [], 'exclusion_analysis': ['Maintenance ended before incident.']})}}]})
    client = NebiusClient(settings, httpx.MockTransport(handler))
    result = await assess(client, system='system', prompt='source evidence')
    assert result.confidence == 0.98


@pytest.mark.parametrize('failure', ['timeout', 'unauthorized', 'rate_limit', 'malformed', 'missing_choices'])
async def test_live_failures_are_reviewable(settings, failure):
    settings.infraclaim_llm_mode = 'live'
    settings.nebius_api_key = 'secret-test-key'
    def handler(request):
        if failure == 'timeout': raise httpx.ReadTimeout('secret provider text')
        if failure == 'unauthorized': return httpx.Response(401, text='secret-test-key')
        if failure == 'rate_limit': return httpx.Response(429)
        if failure == 'missing_choices': return httpx.Response(200, json={})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'invalid JSON'}}]})
    result = await assess(NebiusClient(settings, httpx.MockTransport(handler)), system='system', prompt='evidence')
    assert result.decision == 'needs_review'
    assert result.confidence == 0
    assert 'secret' not in result.model_dump_json()


def test_api_contract_and_restart(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get('/health').json()['version'] == '0.8.0'
        assert client.get('/cases/unknown').status_code == 404
        assert client.post('/demo/investigate/unknown').status_code == 404
        hero = client.post('/demo/investigate/inc_cooling_001').json()
        cid = hero['id']
        assert hero['amount_usd'] == 40000
        assert hero['contract_snapshot']['sla']['source_page'] == 2
        assert client.post('/demo/investigate/inc_cooling_001').json()['id'] == cid
        assert client.post(f'/cases/{cid}/reconcile').status_code == 409
        assert client.post(f'/cases/{cid}/defend').status_code == 409
        vendor = client.post('/vendor/claims', json={'case_id': cid}).json()
        vid = vendor['id']
        assert client.post('/vendor/claims', json={'case_id': cid}).json()['id'] == vid
        assert client.post(f'/vendor/claims/{vid}/simulate-dispute').json()['status'] == 'disputed'
        assert client.post(f'/vendor/claims/{vid}/simulate-accept').status_code == 409
        assert client.post(f'/vendor/claims/{vid}/defense').json()['status'] == 'defended'
        assert client.post(f'/vendor/claims/{vid}/simulate-accept').json()['status'] == 'accepted'
        assert client.get('/recovery-summary').json()['verified_amount_usd'] == 0
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f'/cases/{cid}').json()['state'] == 'accepted'
        assert restarted.post('/watcher/tick').json()['verified_amount_usd'] == 40000
        assert restarted.get(f'/vendor/claims/{vid}/credit-memo').json()['memo']['status'] == 'posted'
        assert restarted.get(f'/cases/{cid}/claim-package').status_code == 200
        ambiguous = restarted.post('/demo/investigate/inc_cooling_ambiguous').json()
        assert ambiguous['state'] == 'human_review'
        assert restarted.post(f"/cases/{ambiguous['id']}/submit").status_code == 409
        assert len(restarted.get('/cases').json()) == 2


async def test_maintenance_union_prevents_double_subtraction():
    from app.domain.entitlement import calculate_entitlement
    incident = load_incidents()[0]
    window = load_incidents()[1].maintenance_windows[0].model_copy(deep=True)
    window.start, window.end = incident.start, incident.start + timedelta(hours=1)
    incident.maintenance_windows = [window, window.model_copy(deep=True)]
    assert calculate_entitlement(load_contract(), incident).capped_amount_usd == 30000


async def test_concurrent_reconciliation_books_once(flow):
    workflow, case_id = flow
    await accepted(flow)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(workflow.reconcile, [case_id] * 5))
    assert all(c.state == CaseState.VERIFIED for c in results)
    assert workflow.store.summary()['verified_cases'] == 1


async def test_transaction_rolls_back_vendor_when_case_save_fails(flow, monkeypatch):
    workflow, case_id = flow
    def fail(*args): raise Conflict('Injected save failure')
    monkeypatch.setattr(workflow.store, 'save', fail)
    with pytest.raises(Conflict):
        workflow.submit(case_id)
    assert workflow.store.get(case_id).state == CaseState.CLAIM_READY
    with workflow.store.transaction() as db:
        assert db.execute('SELECT COUNT(*) FROM vendor_claims').fetchone()[0] == 0


def test_lifespan_worker_finishes_without_manual_tick(settings):
    import time
    settings.watcher_enabled = True
    settings.watcher_interval_seconds = 0.1
    with TestClient(create_app(settings)) as client:
        case = client.post('/demo/investigate/inc_cooling_001').json()
        client.post(f"/cases/{case['id']}/run-loop")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            current = client.get(f"/cases/{case['id']}").json()
            if current['state'] == 'verified': break
            time.sleep(0.1)
        assert current['state'] == 'verified'
        assert client.get('/recovery-summary').json()['verified_amount_usd'] == 40000


def test_bad_pdf_rejected(settings):
    with TestClient(create_app(settings)) as client:
        for payload in [b'not pdf', b'%PDF broken content']:
            assert client.post('/contracts/ingest', files={'file': ('bad.pdf', payload, 'application/pdf')}).status_code == 422


async def test_unknown_pdf_does_not_invent_terms():
    from app.services.contract_ingestion import ContractIngestor
    ingestor = ContractIngestor()
    ingestor._extract_pages = lambda payload: ['Unrelated document with no SLA terms.']
    with pytest.raises(ValueError, match='Unsupported contract template'):
        await ingestor.ingest_pdf(b'%PDF dummy')


async def test_configured_confidence_threshold_is_consistent(settings):
    value = await NebiusClient(settings).reason_json(system='investigation', prompt='fixture')
    value['confidence'] = 0.92
    engine = CaseEngine(BadReasoner(value), settings)
    case = await engine.investigate(load_contract(), load_incidents()[0])
    assert case.state == CaseState.CLAIM_READY
    assert not case.claim_package.approval_required
    assert AutonomyPolicy(settings).evaluate(case, 'submit')['allowed']
    settings.autonomy_min_confidence = 0.95
    assert not AutonomyPolicy(settings).evaluate(case, 'submit')['allowed']

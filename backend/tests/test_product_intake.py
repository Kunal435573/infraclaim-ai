from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.contract_ingestion import load_demo_contract_pdf


def incident(incident_id, ambiguous=False):
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=1)
    end = start + timedelta(hours=4)
    windows = ([{'start': (start + timedelta(minutes=10)).isoformat(),
                 'end': (start + timedelta(minutes=30)).isoformat(),
                 'description': 'Partially overlapping maintenance'}] if ambiguous else [])
    return {'id': incident_id, 'service': 'critical_cooling_loop_b', 'vendor': 'ThermaCore',
            'start': start.isoformat(), 'end': end.isoformat(), 'severity': 'critical',
            'telemetry': {'pump_state': 'fault', 'coolant_pressure_bar': 1.7},
            'ticket_opened_at': (start + timedelta(minutes=2)).isoformat(),
            'vendor_acknowledged_at': (start + timedelta(minutes=24)).isoformat(),
            'maintenance_windows': windows, 'notes': ['Operator-entered incident.']}


def test_manual_intake_review_and_restart(tmp_path):
    config = Settings(_env_file=None, auth_enabled=False, manual_source_gate=False, database_path=str(tmp_path / 'pilot.db'),
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    with TestClient(create_app(config)) as client:
        contract = client.post('/contracts/demo/ingest').json()['contract']
        saved = client.post('/contracts', json=contract)
        assert saved.status_code == 200
        assert len(client.get('/contracts').json()) == 1
        assert client.post('/contracts', json=contract).status_code == 409
        invalid = {**contract, 'id': 'invalid_contract', 'sla': {**contract['sla'], 'source_quote': ''}}
        assert client.post('/contracts', json=invalid).status_code == 422

        response = client.post('/cases/intake', json={'contract_id': contract['id'],
                                                       'incident': incident('pilot_001')})
        assert response.status_code == 200, response.text
        case = response.json()
        assert case['state'] == 'human_review' and case['source'] == 'manual'
        assert case['claim_package']['approval_required']
        assert case['amount_usd'] == 40000
        assert client.post(f"/cases/{case['id']}/submit").status_code == 409

        review = {'expected_version': case['version'], 'action': 'approve_simulation',
                  'reviewer': 'Pilot reviewer', 'note': 'Checked contract and incident sources.'}
        assert client.post(f"/cases/{case['id']}/review", json={**review, 'reviewer': '  '}).status_code == 422
        approved = client.post(f"/cases/{case['id']}/review", json=review)
        assert approved.status_code == 200, approved.text
        case = approved.json()
        assert case['state'] == 'claim_ready' and case['review_approved']
        assert case['claim_package']['approval_required'] is False
        assert case['reviews'][0]['reviewer'] == 'Pilot reviewer'
        assert client.post(f"/cases/{case['id']}/review", json=review).status_code == 409
        assert client.post(f"/cases/{case['id']}/submit").json()['state'] == 'submitted'

    with TestClient(create_app(config)) as client:
        assert len(client.get('/contracts').json()) == 1
        persisted = client.get(f"/cases/{case['id']}").json()
        assert persisted['state'] == 'submitted' and persisted['reviews'][0]['action'] == 'approve_simulation'


def test_review_cannot_override_conflicting_evidence(tmp_path):
    config = Settings(_env_file=None, auth_enabled=False, manual_source_gate=False, database_path=str(tmp_path / 'review.db'),
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    with TestClient(create_app(config)) as client:
        contract = client.post('/contracts/demo/ingest').json()['contract']
        client.post('/contracts', json=contract)
        case = client.post('/cases/intake', json={'contract_id': contract['id'],
                                                  'incident': incident('pilot_ambiguous', True)}).json()
        assert case['state'] == 'human_review'
        decision = {'expected_version': case['version'], 'action': 'approve_simulation',
                    'reviewer': 'Pilot reviewer', 'note': 'I want this submitted.'}
        assert client.post(f"/cases/{case['id']}/review", json=decision).status_code == 409
        assert client.post(f"/cases/{case['id']}/submit").status_code == 409
        decision['action'] = 'request_information'
        requested = client.post(f"/cases/{case['id']}/review", json=decision).json()
        assert requested['state'] == 'human_review' and len(requested['reviews']) == 1
        decision.update(expected_version=requested['version'], action='reject')
        rejected = client.post(f"/cases/{case['id']}/review", json=decision).json()
        assert rejected['state'] == 'closed' and not rejected['review_approved']


def test_uploaded_contract_pdf_is_linked_and_retrievable_after_restart(tmp_path):
    config = Settings(_env_file=None, auth_enabled=False, manual_source_gate=False, database_path=str(tmp_path / 'documents.db'),
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    pdf = load_demo_contract_pdf()
    with TestClient(create_app(config)) as client:
        parsed = client.post('/contracts/ingest',
                             files={'file': ('source.pdf', pdf, 'application/pdf')})
        assert parsed.status_code == 200, parsed.text
        contract = parsed.json()['contract']
        assert contract['source_document_id'] == parsed.json()['document_id']
        assert contract['source_file_sha256'] == sha256(pdf).hexdigest()
        assert client.get(f"/contracts/{contract['id']}/source").status_code == 404
        assert client.post('/contracts', json=contract).status_code == 200
        source = client.get(f"/contracts/{contract['id']}/source")
        assert source.content == pdf
        assert source.headers['x-content-sha256'] == sha256(pdf).hexdigest()
        reused = {**contract, 'id': 'another_contract'}
        assert client.post('/contracts', json=reused).status_code == 409
        staged = client.post('/contracts/ingest',
                             files={'file': ('stale.pdf', pdf, 'application/pdf')}).json()['contract']
        with client.app.state.store.transaction() as db:
            db.execute('UPDATE contract_documents SET uploaded_at=? WHERE id=?',
                       ('2000-01-01T00:00:00+00:00', staged['source_document_id']))
        assert client.post('/contracts', json={**staged, 'id': 'stale_contract'}).status_code == 409
        assert len(client.get('/contracts').json()) == 1
    with TestClient(create_app(config)) as client:
        assert client.get(f"/contracts/{contract['id']}/source").content == pdf


def test_corrected_incident_reassesses_and_requires_new_review(tmp_path):
    config = Settings(_env_file=None, auth_enabled=False, manual_source_gate=False, database_path=str(tmp_path / 'correction.db'),
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    with TestClient(create_app(config)) as client:
        contract = client.post('/contracts/demo/ingest').json()['contract']
        assert client.post('/contracts', json=contract).status_code == 200
        original = incident('pilot_corrected', True)
        case = client.post('/cases/intake', json={'contract_id': contract['id'],
                                                  'incident': original}).json()
        assert case['state'] == 'human_review'
        requested = client.post(f"/cases/{case['id']}/review", json={
            'expected_version': case['version'], 'action': 'request_information',
            'reviewer': 'Pilot reviewer', 'note': 'Please confirm the maintenance window.'
        }).json()
        corrected = {**original, 'maintenance_windows': [],
                     'notes': ['Operator corrected a mistaken calendar entry.']}
        amendment = {'expected_version': requested['version'], 'incident': corrected,
                     'operator': 'Pilot operator', 'note': 'Calendar showed no scheduled maintenance.'}
        assert client.post(f"/cases/{case['id']}/amend",
                           json={**amendment, 'expected_version': case['version']}).status_code == 409
        response = client.post(f"/cases/{case['id']}/amend", json=amendment)
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated['id'] == case['id'] and updated['state'] == 'human_review'
        assert updated['amount_usd'] == 40000 and updated['review_approved'] is False
        assert updated['claim_package'] is None
        assert len(updated['amendments']) == 1 and len(updated['reviews']) == 1
        assert updated['amendments'][0]['previous_incident']['maintenance_windows']
        assert updated['amendments'][0]['updated_incident']['maintenance_windows'] == []
        approved = client.post(f"/cases/{case['id']}/review", json={
            'expected_version': updated['version'], 'action': 'approve_simulation',
            'reviewer': 'Pilot reviewer', 'note': 'Checked corrected maintenance calendar.'
        })
        assert approved.status_code == 200, approved.text
        assert approved.json()['state'] == 'claim_ready'
        assert client.post(f"/cases/{case['id']}/amend", json={
            **amendment, 'expected_version': approved.json()['version']}).status_code == 409

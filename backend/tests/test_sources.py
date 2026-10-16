from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.test_product_intake import incident
from app.services.repository import load_incidents


def test_manual_approval_requires_distinct_reviewed_sources(tmp_path):
    config = Settings(_env_file=None, database_path=str(tmp_path / 'sources.db'),
                      auth_enabled=True, manual_source_gate=True,
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    app = create_app(config)
    app.state.auth.create_user('operator1', 'Pilot Operator', 'operator', 'operator-password-12345')
    app.state.auth.create_user('reviewer1', 'Pilot Reviewer', 'reviewer', 'reviewer-password-12345')
    with TestClient(app) as operator, TestClient(app) as reviewer:
        operator.post('/auth/login', json={'username': 'operator1', 'password': 'operator-password-12345'})
        reviewer.post('/auth/login', json={'username': 'reviewer1', 'password': 'reviewer-password-12345'})
        contract = operator.post('/contracts/demo/ingest').json()['contract']
        assert operator.post('/contracts', json=contract).status_code == 200
        case = operator.post('/cases/intake', json={'contract_id': contract['id'],
                                                    'incident': incident('sources_001')}).json()
        base = {'expected_version': case['version'], 'action': 'approve_simulation',
                'note': 'Checked source exports and contract.'}
        assert reviewer.post(f"/cases/{case['id']}/review", json=base).status_code == 409
        ids = []
        for category in ('ticket', 'telemetry', 'maintenance'):
            payload = f'synthetic {category} export'.encode()
            response = operator.post(f"/cases/{case['id']}/sources", data={'category': category},
                                     files={'file': (f'{category}.txt', payload, 'text/plain')})
            assert response.status_code == 200, response.text
            case = response.json()['case']
            document = response.json()['document']
            ids.append(document['id'])
            assert document['sha256'] == sha256(payload).hexdigest()
            downloaded = reviewer.get(f"/cases/{case['id']}/sources/{document['id']}")
            assert downloaded.content == payload
        assert len(reviewer.get(f"/cases/{case['id']}/sources").json()) == 3
        base['expected_version'] = case['version']
        base['verified_source_ids'] = ids
        base['source_check_note'] = 'Compared each synthetic export with its entered incident field.'
        assert reviewer.post(f"/cases/{case['id']}/review", json={**base, 'verified_source_ids': ids[:2]}).status_code == 409
        approved = reviewer.post(f"/cases/{case['id']}/review", json=base)
        assert approved.status_code == 200, approved.text
        assert approved.json()['state'] == 'claim_ready'
        assert {item['id'] for item in approved.json()['reviews'][0]['verified_sources']} == set(ids)
        assert operator.post(f"/cases/{case['id']}/sources", data={'category': 'ticket'},
                             files={'file': ('late.txt', b'late', 'text/plain')}).status_code == 409


def test_pilot_sample_sources_detect_mislabel_and_mismatched_incident(tmp_path):
    config = Settings(_env_file=None, database_path=str(tmp_path / 'pilot-sources.db'),
                      auth_enabled=True, manual_source_gate=True,
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    app = create_app(config)
    app.state.auth.create_user('operator1', 'Pilot Operator', 'operator', 'operator-password-12345')
    app.state.auth.create_user('reviewer1', 'Pilot Reviewer', 'reviewer', 'reviewer-password-12345')
    with TestClient(app) as operator, TestClient(app) as reviewer:
        operator.post('/auth/login', json={'username': 'operator1', 'password': 'operator-password-12345'})
        reviewer.post('/auth/login', json={'username': 'reviewer1', 'password': 'reviewer-password-12345'})
        contract = operator.post('/contracts/demo/ingest').json()['contract']
        assert operator.post('/contracts', json=contract).status_code == 200
        sample = load_incidents()[0].model_dump(mode='json')
        sample['id'] = 'pilot_manual_001'
        case = operator.post('/cases/intake', json={'contract_id': contract['id'], 'incident': sample}).json()
        path = f"/cases/{case['id']}/sources/pilot-fixtures"
        assert reviewer.post(path).status_code == 403
        first = operator.post(path)
        assert first.status_code == 200, first.text
        assert len(first.json()['sources']) == 3
        assert all(item['analysis'] == {'recognized': True, 'findings': []}
                   for item in first.json()['sources'])
        assert len(operator.post(path).json()['sources']) == 3
        wrong = operator.post(f"/cases/{case['id']}/sources", data={'category': 'maintenance'},
                              files={'file': ('telemetry-synthetic.csv',
                                (Path(__file__).resolve().parents[1] /
                                 'app/data/incident_sources/telemetry-synthetic.csv').read_bytes(), 'text/csv')})
        assert wrong.status_code == 200
        checks = operator.get(f"/cases/{case['id']}/sources").json()
        assert any('labelled maintenance' in ' '.join(item['analysis']['findings']) for item in checks)
        changed = dict(sample)
        changed['vendor_acknowledged_at'] = datetime(2026, 10, 13, 11, 29, tzinfo=timezone.utc).isoformat()
        amended = operator.post(f"/cases/{case['id']}/amend", json={
            'expected_version': wrong.json()['case']['version'], 'incident': changed,
            'note': 'Testing mismatched source time.'})
        assert amended.status_code == 200, amended.text
        checks = reviewer.get(f"/cases/{case['id']}/sources").json()
        assert any('Vendor acknowledgement time differs' in ' '.join(item['analysis']['findings'])
                   for item in checks)
        ids = [item['id'] for item in checks if item['category'] != 'maintenance'
               or item['filename'] == 'maintenance-synthetic.json']
        response = reviewer.post(f"/cases/{case['id']}/review", json={
            'expected_version': amended.json()['version'], 'action': 'approve_simulation',
            'note': 'Compared all sample source files.', 'verified_source_ids': ids,
            'source_check_note': 'Compared the three synthetic exports with the entered incident.'})
        assert response.status_code == 409
        assert 'Vendor acknowledgement time differs' in response.json()['detail']


def test_matching_pilot_exports_can_be_approved_by_separate_reviewer(tmp_path):
    config = Settings(_env_file=None, database_path=str(tmp_path / 'matching-pilot.db'),
                      auth_enabled=True, manual_source_gate=True,
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    app = create_app(config)
    app.state.auth.create_user('operator1', 'Pilot Operator', 'operator', 'operator-password-12345')
    app.state.auth.create_user('reviewer1', 'Pilot Reviewer', 'reviewer', 'reviewer-password-12345')
    with TestClient(app) as operator, TestClient(app) as reviewer:
        operator.post('/auth/login', json={'username': 'operator1', 'password': 'operator-password-12345'})
        reviewer.post('/auth/login', json={'username': 'reviewer1', 'password': 'reviewer-password-12345'})
        contract = operator.post('/contracts/demo/ingest').json()['contract']
        assert operator.post('/contracts', json=contract).status_code == 200
        sample = load_incidents()[0].model_dump(mode='json')
        sample['id'] = 'pilot_manual_001'
        case = operator.post('/cases/intake', json={'contract_id': contract['id'], 'incident': sample}).json()
        attached = operator.post(f"/cases/{case['id']}/sources/pilot-fixtures").json()
        approved = reviewer.post(f"/cases/{case['id']}/review", json={
            'expected_version': attached['case']['version'], 'action': 'approve_simulation',
            'note': 'Checked all three sample exports and contract.',
            'verified_source_ids': [item['id'] for item in attached['sources']],
            'source_check_note': 'Compared all three synthetic exports with the entered incident fields.'})
        assert approved.status_code == 200, approved.text
        assert approved.json()['state'] == 'claim_ready'

"""Regression coverage for the October security audit; isolated synthetic data only."""
import asyncio
import copy
import io
import json
import math
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfWriter
from app.config import Settings
from app.main import create_app
from app.schemas import VendorContract
from app.services.contract_ingestion import ContractIngestor, load_demo_contract_pdf
from app.services.repository import load_incidents, load_contract
from app.services.source_checks import check_source
from app.services.nebius import NebiusClient, InferenceError
from app.security import BoundedBodyMiddleware

PASSWORD = 'synthetic-security-test-password'


@pytest.fixture
def secured(tmp_path):
    settings = Settings(_env_file=None, database_path=str(tmp_path/'security.db'),
                        auth_enabled=True, self_signup_enabled=True, watcher_enabled=False,
                        infraclaim_llm_mode='mock', nebius_api_key=None, credit_delay_seconds=0)
    app = create_app(settings)
    for role in ['admin', 'operator', 'reviewer']:
        app.state.auth.create_user(role, role.title(), role, PASSWORD)
    return app


def login(app, role):
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post('/auth/login', json={'username': role, 'password': PASSWORD}).status_code == 200
    return client


@pytest.mark.parametrize('role', ['operator', 'reviewer'])
@pytest.mark.parametrize('path', ['/vendor/claims', '/vendor/claims/unknown/simulate-dispute',
    '/vendor/claims/unknown/defense', '/vendor/claims/unknown/simulate-accept', '/watcher/tick',
    '/cases/unknown/reconcile', '/cases/unknown/run-loop'])
def test_all_vendor_aliases_require_admin(secured, role, path):
    with login(secured, role) as client:
        assert client.post(path, json={'case_id': 'unknown'}).status_code == 403
    with secured.state.store.transaction() as db:
        assert db.execute('SELECT count(*) FROM vendor_claims').fetchone()[0] == 0


def test_admin_workflow_still_completes(secured):
    with login(secured, 'admin') as client:
        case = client.post('/demo/investigate/inc_cooling_001').json()
        vendor = client.post('/vendor/claims', json={'case_id': case['id']})
        assert vendor.status_code == 200
        for action in ['simulate-dispute', 'defense', 'simulate-accept']:
            assert client.post(f"/vendor/claims/{vendor.json()['id']}/{action}").status_code == 200
        assert client.post('/watcher/tick').status_code == 200
        assert client.get(f"/cases/{case['id']}").json()['state'] == 'verified'
        summary = client.get('/recovery-summary').json()
        client.post('/watcher/tick')
        assert client.get('/recovery-summary').json() == summary


def test_signup_cannot_read_shared_data_until_admin_approves(secured):
    with login(secured, 'admin') as admin, TestClient(secured) as newcomer:
        case = admin.post('/demo/investigate/inc_cooling_001').json()
        result = newcomer.post('/auth/signup', json={'username':'new_user', 'display_name':'New User', 'password':PASSWORD, 'role':'admin'})
        assert result.status_code == 202 and 'set-cookie' not in result.headers
        assert newcomer.post('/auth/login', json={'username':'new_user','password':PASSWORD}).status_code == 401
        for path in ['/cases', f"/cases/{case['id']}", '/contracts', '/admin/users']:
            assert newcomer.get(path).status_code == 401
        assert admin.post('/admin/users/new_user/state', json={'disabled':False}).status_code == 200
        assert newcomer.post('/auth/login', json={'username':'new_user','password':PASSWORD}).status_code == 200
        assert newcomer.get('/auth/me').json()['role'] == 'operator'
        assert newcomer.post('/vendor/claims',json={'case_id':case['id']}).status_code == 403


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), -1, 0, 1e20])
def test_bad_money_never_persists(secured, value):
    with login(secured, 'operator') as client:
        contract = load_contract().model_dump(mode='json')
        contract['sla']['rate_per_eligible_hour_usd'] = value
        response = client.post('/contracts', content=json.dumps(contract), headers={'content-type':'application/json'})
        assert response.status_code == 422
        assert client.get('/contracts').status_code == 200
        assert client.get('/contracts').json() == []
        assert 'input' not in response.text


def test_serialized_contract_rechecked_before_commit(secured):
    contract = load_contract()
    contract.sla.rate_per_eligible_hour_usd = float('nan')
    with pytest.raises(ValidationError):
        secured.state.store.create_contract(contract)
    assert secured.state.store.list_contracts() == []


def test_malformed_sources_rejected_and_old_records_fail_safely(secured):
    with login(secured,'operator') as client:
        contract = client.post('/contracts/demo/ingest').json()['contract']
        client.post('/contracts', json=contract)
        incident = load_incidents()[0].model_dump(mode='json')
        incident['id'] = 'malformed_security_test'
        incident['maintenance_windows'] = [{'start':'2026-10-05T12:00:00Z','end':'2026-10-05T13:00:00Z','description':'Synthetic'}]
        case = client.post('/cases/intake',json={'contract_id':contract['id'],'incident':incident}).json()
        body = {'synthetic_fixture':True,'incident_id':incident['id'],'windows':[dict(incident['maintenance_windows'][0],description=42)]}
        payload = json.dumps(body).encode()
        url = f"/cases/{case['id']}/sources"
        response = client.post(url,data={'category':'maintenance'},files={'file':('bad.json',payload,'application/json')})
        assert response.status_code == 422
        assert client.get(url).json() == []
        # Simulate an invalid pre-fix record without changing a user's real data.
        with secured.state.store.transaction() as db:
            db.execute('INSERT INTO incident_documents VALUES(?,?,?,?,?,?,?,?)',
                ('legacy_bad',case['id'],'maintenance','bad.json','synthetic',payload,'2026-10-15T00:00:00Z','operator'))
        listing = client.get(url)
        assert listing.status_code == 200
        assert listing.json()[0]['analysis']['invalid'] is True
        assert listing.json()[0]['analysis']['findings']


@pytest.mark.parametrize('origin', ['null','https://untrusted.example','not-a-url','http://localhost:3000/evil'])
def test_backend_rejects_untrusted_origins(secured, origin):
    with TestClient(secured) as client:
        assert client.post('/auth/login',headers={'origin':origin},json={'username':'operator','password':PASSWORD}).status_code == 403


def test_five_bad_passwords_do_not_lock_victim(secured):
    with TestClient(secured) as client:
        for _ in range(5):
            assert client.post('/auth/login',json={'username':'operator','password':'wrong'}).status_code == 401
        assert client.post('/auth/login',json={'username':'operator','password':PASSWORD}).status_code == 200


def test_login_rate_limit_and_untrusted_forwarded_address(secured):
    # Fix elapsed time so slow password hashing cannot refill the bucket mid-test.
    secured.state.rate_limits.clock = lambda: 0.0
    with TestClient(secured) as client:
        statuses = [client.post('/auth/login',headers={'x-forwarded-for':f'192.0.2.{i}'},json={'username':'missing','password':'wrong'}).status_code for i in range(31)]
        assert statuses[:30] == [401]*30
        assert statuses[-1] == 429


def test_pagination_is_bounded(secured):
    with login(secured,'operator') as client:
        assert client.get('/cases?limit=201').status_code == 422
        assert client.get('/contracts?offset=-1').status_code == 422
        assert client.get('/cases?limit=1&offset=0').json() == []


def test_hosted_requires_secure_authentication(tmp_path):
    with pytest.raises(ValidationError):
        Settings(_env_file=None,infraclaim_deployment='hosted',auth_cookie_secure=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None,infraclaim_deployment='hosted',auth_cookie_secure=True,auth_enabled=False)
    config=Settings(_env_file=None,infraclaim_deployment='hosted',auth_cookie_secure=True,
                    database_path=str(tmp_path/'hosted.db'),watcher_enabled=False)
    app=create_app(config);app.state.auth.create_user('admin','Admin','admin',PASSWORD)
    with TestClient(app,base_url='https://testserver') as client:
        response=client.post('/auth/login',json={'username':'admin','password':PASSWORD})
        assert 'Secure' in response.headers['set-cookie']
        assert 'HttpOnly' in response.headers['set-cookie']
        assert 'SameSite=strict' in response.headers['set-cookie']
        assert client.get('/cases').status_code==200


async def test_body_cap_counts_actual_stream_before_application():
    reached=[];sent=[]
    async def downstream(scope,receive,send):reached.append(True)
    middleware=BoundedBodyMiddleware(downstream,max_json_bytes=20)
    incoming=iter([{'type':'http.request','body':b'A'*15,'more_body':True},
                   {'type':'http.request','body':b'B'*15,'more_body':False}])
    async def receive():return next(incoming)
    async def send(message):sent.append(message)
    await middleware({'type':'http','method':'POST','headers':[(b'content-type',b'application/json')]},receive,send)
    assert not reached
    assert sent[0]['status']==413


async def test_pdf_page_budget():
    writer=PdfWriter()
    for _ in range(51):writer.add_blank_page(width=72,height=72)
    output=io.BytesIO();writer.write(output)
    with pytest.raises(ValueError):
        await ContractIngestor().ingest_pdf(output.getvalue())


async def test_full_provider_queue_fails_closed_without_network():
    config=Settings(_env_file=None,infraclaim_llm_mode='live',nebius_api_key='synthetic-key')
    client=NebiusClient(config)
    await client._slots.acquire();await client._slots.acquire()
    try:
        with pytest.raises(InferenceError,match='provider_busy'):
            await client.reason_json(system='rules',prompt='synthetic')
    finally:
        client._slots.release();client._slots.release()

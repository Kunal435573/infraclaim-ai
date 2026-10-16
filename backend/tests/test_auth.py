from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.test_product_intake import incident


def test_identity_roles_and_audit(tmp_path):
    config = Settings(_env_file=None, database_path=str(tmp_path / 'auth.db'),
                      auth_enabled=True, manual_source_gate=False,
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    app = create_app(config)
    app.state.auth.create_user('operator1', 'Pilot Operator', 'operator', 'operator-test-password-123')
    app.state.auth.create_user('reviewer1', 'Pilot Reviewer', 'reviewer', 'reviewer-test-password-123')
    with TestClient(app) as anonymous, TestClient(app) as operator, TestClient(app) as reviewer:
        assert anonymous.get('/cases').status_code == 401
        assert anonymous.post('/cases/intake', json={}).status_code == 401
        assert operator.post('/auth/login', json={'username': 'operator1', 'password': 'wrong'}).status_code == 401
        signed = operator.post('/auth/login', json={'username': 'operator1', 'password': 'operator-test-password-123'})
        assert signed.status_code == 200
        assert 'httponly' in signed.headers['set-cookie'].lower()
        assert operator.get('/auth/me').json()['role'] == 'operator'
        assert reviewer.post('/auth/login', json={'username': 'reviewer1', 'password': 'reviewer-test-password-123'}).status_code == 200
        assert reviewer.post('/contracts', json={}).status_code == 403
        contract = operator.post('/contracts/demo/ingest').json()['contract']
        assert operator.post('/contracts', json=contract).status_code == 200
        case = operator.post('/cases/intake', json={'contract_id': contract['id'],
                                                   'incident': incident('auth_001')}).json()
        assert operator.post(f"/cases/{case['id']}/review", json={
            'expected_version': case['version'], 'action': 'approve_simulation',
            'reviewer': 'forged reviewer', 'note': 'Checked the source records.'}).status_code == 403
        assert reviewer.post(f"/cases/{case['id']}/amend", json={}).status_code == 403
        approved = reviewer.post(f"/cases/{case['id']}/review", json={
            'expected_version': case['version'], 'action': 'approve_simulation',
            'reviewer': 'forged reviewer', 'note': 'Checked the source records.'})
        assert approved.status_code == 200, approved.text
        assert approved.json()['reviews'][0]['reviewer'] == 'reviewer1'
        assert reviewer.post(f"/cases/{case['id']}/submit").status_code == 403
        corrected_case = operator.post('/cases/intake', json={'contract_id': contract['id'],
                                                              'incident': incident('auth_002')}).json()
        corrected = operator.post(f"/cases/{corrected_case['id']}/amend", json={
            'expected_version': corrected_case['version'], 'incident': corrected_case['incident_snapshot'],
            'operator': 'forged operator', 'note': 'Clarified operator entry.'})
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()['amendments'][0]['operator'] == 'operator1'
        assert operator.post('/auth/logout').status_code == 200
        assert operator.get('/cases').status_code == 401


def test_admin_account_lifecycle_revokes_sessions(tmp_path):
    config = Settings(_env_file=None, database_path=str(tmp_path / 'users.db'),
                      auth_enabled=True, infraclaim_llm_mode='mock', watcher_enabled=False)
    app = create_app(config)
    app.state.auth.create_user('admin1', 'First Admin', 'admin', 'admin-password-12345')
    with TestClient(app) as admin, TestClient(app) as operator:
        assert admin.post('/auth/login', json={'username': 'admin1', 'password': 'admin-password-12345'}).status_code == 200
        created = admin.post('/admin/users', json={'username': 'operator1', 'display_name': 'Operator One',
                                                    'role': 'operator', 'password': 'operator-password-12345'})
        assert created.status_code == 200, created.text
        assert operator.post('/auth/login', json={'username': 'operator1',
                                                  'password': 'operator-password-12345'}).status_code == 200
        assert operator.get('/admin/users').status_code == 403
        assert admin.post('/admin/users/admin1/state', json={'disabled': True}).status_code == 409
        assert admin.post('/admin/users/operator1/password', json={'password': 'new-password-123456'}).status_code == 200
        assert operator.get('/cases').status_code == 401
        assert operator.post('/auth/login', json={'username': 'operator1',
                                                  'password': 'operator-password-12345'}).status_code == 401
        assert operator.post('/auth/login', json={'username': 'operator1',
                                                  'password': 'new-password-123456'}).status_code == 200
        assert admin.post('/admin/users/operator1/state', json={'disabled': True}).status_code == 200
        assert operator.get('/cases').status_code == 401
        assert operator.post('/auth/login', json={'username': 'operator1',
                                                  'password': 'new-password-123456'}).status_code == 401
        assert any(item['action'] == 'disabled' for item in admin.get('/admin/auth-events').json())


def test_local_signup_requires_admin_approval(tmp_path):
    config = Settings(_env_file=None, database_path=str(tmp_path / 'signup.db'),
                      auth_enabled=True, self_signup_enabled=True,
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    app = create_app(config)
    with TestClient(app) as browser:
        assert browser.get('/auth/signup-status').json() == {'enabled': True}
        response = browser.post('/auth/signup', json={
            'username': 'new_operator', 'display_name': 'New Operator',
            'password': 'a-long-private-password-123', 'role': 'admin'})
        assert response.status_code == 202, response.text
        assert response.json()['pending_approval'] is True
        assert 'set-cookie' not in response.headers
        assert browser.get('/cases').status_code == 401
        assert browser.post('/auth/login', json={'username': 'new_operator', 'password': 'a-long-private-password-123'}).status_code == 401
        assert app.state.auth.list_users()[0]['role'] == 'operator'
        app.state.auth.set_disabled('new_operator', False, 'test_admin')
        assert browser.post('/auth/login', json={'username': 'new_operator', 'password': 'a-long-private-password-123'}).status_code == 200
        assert browser.get('/auth/me').json()['username'] == 'new_operator'
        assert browser.get('/cases').status_code == 200
        assert browser.get('/admin/users').status_code == 403
        assert browser.post('/cases/unknown/review', json={}).status_code == 403
        assert browser.post('/auth/signup', json={
            'username': 'new_operator', 'display_name': 'Again',
            'password': 'a-long-private-password-123'}).status_code == 409
        assert any(event['action'] == 'signup_requested' for event in app.state.auth.events())


def test_signup_is_off_by_default_and_cannot_choose_privileged_role(tmp_path):
    config = Settings(_env_file=None, database_path=str(tmp_path / 'closed-signup.db'),
                      auth_enabled=True, self_signup_enabled=False,
                      infraclaim_llm_mode='mock', watcher_enabled=False)
    app = create_app(config)
    with TestClient(app) as browser:
        assert browser.get('/auth/signup-status').json() == {'enabled': False}
        assert browser.post('/auth/signup', json={
            'username': 'new_operator', 'display_name': 'New Operator',
            'password': 'a-long-private-password-123'}).status_code == 403
        assert browser.get('/cases').status_code == 401

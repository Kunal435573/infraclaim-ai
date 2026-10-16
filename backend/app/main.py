import asyncio
import sqlite3
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from typing import Literal
from app.config import get_settings
from app.schemas import CaseState, InfrastructureIncident, VendorContract, CaseEvent
from app.services.case_engine import CaseEngine
from app.services.contract_ingestion import ContractIngestor, load_demo_contract_pdf
from app.services.repository import load_incidents
from app.services.store import Store, Conflict
from app.services.workflow import Workflow
from app.services.auth import Auth
from app.services.source_checks import check_source
from app.security import PUBLIC, authorize, origin_allowed, RateLimits, BoundedBodyMiddleware


class VendorSubmission(BaseModel):
    case_id: str


class ManualIntake(BaseModel):
    contract_id: str = Field(min_length=1, max_length=160)
    incident: InfrastructureIncident


class ReviewRequest(BaseModel):
    expected_version: int = Field(ge=0)
    action: Literal['approve_simulation', 'reject', 'request_information']
    reviewer: str = ''
    note: str = Field(min_length=5, max_length=2000)
    verified_source_ids: list[str] = Field(default_factory=list, max_length=10)
    source_check_note: str = Field(default='', max_length=2000)


class AmendmentRequest(BaseModel):
    expected_version: int = Field(ge=0)
    incident: InfrastructureIncident
    operator: str = ''
    note: str = Field(min_length=5, max_length=2000)


def create_app(settings=None, nebius=None):
    settings = settings or get_settings()
    engine = CaseEngine(nebius, settings)
    ingestor = ContractIngestor(engine.nebius)
    store = Store(settings.database_path)
    auth = Auth(store)
    workflow = Workflow(store, engine, settings)

    @asynccontextmanager
    async def lifespan(app):
        worker = asyncio.create_task(workflow.watch()) if settings.watcher_enabled else None
        try:
            yield
        finally:
            if worker:
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker

    async def permission(request: Request):
        authorize(request, settings.auth_enabled)

    app = FastAPI(title='InfraClaim AI — internal pilot', version='0.8.1', lifespan=lifespan,
                  dependencies=[Depends(permission)])
    app.state.store, app.state.workflow = store, workflow
    app.state.auth = auth
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
    limits = RateLimits()
    app.state.rate_limits = limits

    @app.middleware('http')
    async def require_session(request: Request, call_next):
        if request.method == 'POST' and not origin_allowed(request, settings.cors_origins):
            return JSONResponse(status_code=403, content={'detail': 'Cross-origin actions are not allowed.'})
        peer = request.client.host if request.client else 'unknown'
        if request.method == 'POST' and request.url.path in {'/auth/login', '/auth/signup'}:
            capacity = 5 if request.url.path == '/auth/signup' else 30
            if not limits.allow(('auth', request.url.path, peer), capacity, 60) or not limits.allow(('auth-global',), 120, 60):
                return JSONResponse(status_code=429, content={'detail': 'Too many attempts. Retry later.'}, headers={'Retry-After': '60'})
        if settings.auth_enabled and request.url.path not in PUBLIC:
            identity = auth.user(request.cookies.get('infraclaim_session'))
            if not identity:
                return JSONResponse(status_code=401, content={'detail': 'Sign in to continue.'})
            request.state.identity = identity
            if request.method == 'POST':
                if not limits.allow(('write', identity['username']), 60, 60):
                    return JSONResponse(status_code=429, content={'detail': 'Write limit reached. Retry later.'}, headers={'Retry-After': '60'})
                if request.url.path.startswith('/demo/investigate/') or request.url.path == '/cases/intake' or request.url.path.endswith(('/amend', '/defend', '/defense')):
                    if not limits.allow(('inference', identity['username']), 20, 3600):
                        return JSONResponse(status_code=429, content={'detail': 'Assessment budget reached. Retry later.'}, headers={'Retry-After': '180'})
        return await call_next(request)

    app.add_middleware(BoundedBodyMiddleware)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Never reflect passwords, non-finite numbers, or oversized hostile input.
        return JSONResponse(status_code=422, content={'detail': 'Invalid request fields.', 'errors': [
            {'loc': list(item['loc']), 'type': item['type']} for item in exc.errors()[:20]]})

    class LoginRequest(BaseModel):
        username: str = Field(min_length=1, max_length=64)
        password: str = Field(min_length=1, max_length=1024)

    class SignupRequest(BaseModel):
        username: str = Field(min_length=3, max_length=64)
        display_name: str = Field(min_length=2, max_length=100)
        password: str = Field(min_length=14, max_length=1024)

    def session_response(token, identity):
        response = JSONResponse(identity)
        response.set_cookie('infraclaim_session', token, max_age=12 * 3600,
                            httponly=True, secure=settings.auth_cookie_secure,
                            samesite='strict', path='/')
        return response

    @app.get('/auth/signup-status')
    def signup_status():
        return {'enabled': settings.auth_enabled and settings.self_signup_enabled}

    @app.post('/auth/signup')
    def signup(body: SignupRequest):
        if not settings.auth_enabled or not settings.self_signup_enabled:
            raise HTTPException(403, 'Self sign-up is disabled. Ask an administrator for an account.')
        try:
            auth.create_user(body.username, body.display_name, 'operator', body.password,
                             actor='self_signup', disabled=True)
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Username already exists.')
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return JSONResponse(status_code=202, content={'pending_approval': True,
                            'message': 'Account requested. An administrator must approve access before you can sign in.'})

    @app.post('/auth/login')
    def login(body: LoginRequest):
        result = auth.login(body.username, body.password)
        if not result:
            raise HTTPException(401, 'Invalid credentials or account not approved.')
        token, identity = result
        return session_response(token, identity)

    @app.get('/auth/me')
    def me(request: Request):
        return request.state.identity if settings.auth_enabled else {'username': 'demo', 'display_name': 'Demo user', 'role': 'admin'}

    @app.post('/auth/logout')
    def logout(request: Request):
        auth.logout(request.cookies.get('infraclaim_session'))
        response = JSONResponse({'signed_out': True})
        response.delete_cookie('infraclaim_session', path='/')
        return response

    class NewUser(BaseModel):
        username: str = Field(min_length=3, max_length=64)
        display_name: str = Field(min_length=2, max_length=100)
        role: Literal['admin', 'operator', 'reviewer']
        password: str = Field(min_length=14, max_length=1024)

    class AccountState(BaseModel):
        disabled: bool

    class PasswordReset(BaseModel):
        password: str = Field(min_length=14, max_length=1024)

    @app.get('/admin/users')
    def list_users():
        return auth.list_users()

    @app.post('/admin/users')
    def add_user(body: NewUser, request: Request):
        try:
            auth.create_user(body.username, body.display_name, body.role, body.password,
                             actor=request.state.identity['username'])
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Username already exists.')
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'created': body.username.strip().lower()}

    @app.post('/admin/users/{username}/state')
    def account_state(username: str, body: AccountState, request: Request):
        try:
            auth.set_disabled(username, body.disabled, request.state.identity['username'])
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'username': username.lower(), 'disabled': body.disabled}

    @app.post('/admin/users/{username}/password')
    def account_password(username: str, body: PasswordReset, request: Request):
        try:
            auth.reset_password(username, body.password, request.state.identity['username'])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'username': username.lower(), 'sessions_revoked': True}

    @app.get('/admin/auth-events')
    def auth_events():
        return auth.events()

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(status_code=404, content={'detail': str(exc).strip("'")})

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'infraclaim-api', 'version': '0.8.0',
                'llm_mode': settings.infraclaim_llm_mode, 'vendor_mode': 'simulated',
                'business_time': settings.demo_now, 'watcher_enabled': settings.watcher_enabled}

    @app.get('/ai/runtime')
    def runtime():
        return engine.nebius.runtime()

    @app.get('/ready')
    def readiness():
        configured = engine.nebius.runtime()['configured']
        return JSONResponse(status_code=200 if configured else 503,
                            content={'ready': configured, 'inference_verified': False,
                                     'vendor_mode': 'simulated'})

    @app.post('/evaluations/run')
    async def evaluation(count: int = Query(50, ge=5, le=200)):
        if not settings.evaluation_api_enabled:
            raise HTTPException(403, 'Evaluation API is disabled; use the local evaluation command')
        from app.services.evaluation import run_evaluation
        from app.services.repository import load_contract
        return await run_evaluation(load_contract(), engine, count)

    @app.post('/contracts/demo/ingest')
    async def ingest_demo():
        return await ingestor.ingest_pdf(load_demo_contract_pdf(), 'ThermaCore_Master_Service_Agreement_2026.pdf')

    @app.get('/demo/context')
    async def context():
        result = await ingest_demo()
        return {'contract': result.contract, 'incidents': load_incidents()}

    @app.post('/contracts/ingest')
    async def ingest(file: UploadFile = File(...)):
        if file.content_type not in {'application/pdf', 'application/octet-stream'}:
            raise HTTPException(415, 'Only PDF contracts are supported')
        payload = await file.read(10 * 1024 * 1024 + 1)
        if len(payload) > 10 * 1024 * 1024:
            raise HTTPException(413, 'Maximum PDF size is 10 MB')
        try:
            result = await ingestor.ingest_pdf(payload, file.filename or 'contract.pdf')
            document = store.stage_contract_document(payload, file.filename or 'contract.pdf')
            result.contract.source_document_id = document['id']
            result.contract.source_file_sha256 = document['sha256']
            result.document_id = document['id']
            return result
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/contracts')
    def contracts(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0, le=1000000)):
        return store.list_contracts(limit=limit, offset=offset)

    @app.get('/contracts/{contract_id}/source')
    def contract_source(contract_id: str):
        document = store.contract_document(contract_id)
        return Response(content=document['payload'], media_type='application/pdf',
                        headers={'Content-Disposition': 'attachment; filename="contract-source.pdf"',
                                 'X-Content-Type-Options': 'nosniff',
                                 'Cache-Control': 'private, no-store',
                                 'X-Content-SHA256': document['sha256']})

    @app.post('/contracts')
    def save_contract(contract: VendorContract):
        sla = contract.sla
        if (not all(value.strip() for value in [contract.id, contract.customer, contract.vendor,
                                                  sla.id, sla.title, sla.service])
                or contract.effective_date.utcoffset() is None
                or sla.rate_per_eligible_hour_usd <= 0 or sla.cap_usd <= 0 or sla.claim_window_days <= 0
                or not sla.response_minutes or not sla.repair_minutes
                or 'planned maintenance' not in sla.exclusions
                or not sla.source_section or not sla.source_quote or len(sla.source_quote) > 4000):
            raise HTTPException(422, 'This pilot requires a sourced hourly-credit SLA with response, repair, cap, claim window and planned-maintenance terms.')
        return store.create_contract(contract)

    @app.post('/cases/intake')
    async def intake(body: ManualIntake):
        contract = store.get_contract(body.contract_id)
        incident = body.incident
        validate_incident(contract, incident)
        if store.for_incident(incident.id):
            raise HTTPException(409, 'An incident with this ID already has a case.')
        case = await engine.investigate(contract, incident, source='manual')
        if case.state == CaseState.CLAIM_READY:
            case.state = CaseState.HUMAN_REVIEW
            case.human_review_reason = 'Manual intake requires human review before simulated vendor submission.'
            case.claim_package.approval_required = True
            case.timeline.append(CaseEvent(at=datetime.now(timezone.utc), state=CaseState.HUMAN_REVIEW,
                                           message=case.human_review_reason))
        case.auto_run = False
        return store.create(case)

    def validate_incident(contract, incident):
        if not incident.id.strip() or not incident.telemetry or len(incident.maintenance_windows) > 25:
            raise HTTPException(422, 'An incident ID, entered telemetry, and at most 25 maintenance windows are required.')
        moments = [contract.effective_date, incident.start, incident.end,
                   incident.ticket_opened_at, incident.vendor_acknowledged_at]
        for window in incident.maintenance_windows:
            moments.extend([window.start, window.end])
            if window.end <= window.start:
                raise HTTPException(422, 'Maintenance end must be after its start.')
        if any(moment.utcoffset() is None for moment in moments):
            raise HTTPException(422, 'All dates and times must include a timezone.')
        if incident.end <= incident.start or incident.vendor_acknowledged_at < incident.ticket_opened_at:
            raise HTTPException(422, 'Check incident start/end and ticket/acknowledgement times.')

    @app.post('/demo/investigate/{incident_id}')
    async def investigate(incident_id: str):
        incidents = {i.id: i for i in load_incidents()}
        if incident_id not in incidents:
            raise HTTPException(404, 'incident not found')
        existing = store.for_incident(incident_id)
        if existing:
            return existing
        result = await ingest_demo()
        return store.create(await engine.investigate(result.contract, incidents[incident_id]))

    @app.get('/cases')
    def cases(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0, le=1000000)):
        return store.list(limit=limit, offset=offset)

    @app.get('/cases/{case_id}/sources')
    def case_sources(case_id: str):
        case = store.get(case_id)
        documents = store.list_incident_documents(case_id)
        for document in documents:
            document['analysis'] = check_source(store.incident_document(case_id, document['id']),
                                                case.incident_snapshot)
        return documents

    @app.post('/cases/{case_id}/sources/pilot-fixtures')
    def add_pilot_sources(case_id: str, request: Request):
        case = store.get(case_id)
        if case.incident_id != 'pilot_manual_001' or case.source != 'manual' or case.state != CaseState.HUMAN_REVIEW:
            raise HTTPException(409, 'Pilot sample files only apply to the open pilot_manual_001 case.')
        fixture_dir = Path(__file__).resolve().parent / 'data' / 'incident_sources'
        fixtures = {'ticket': 'ticket-synthetic.json', 'telemetry': 'telemetry-synthetic.csv',
                    'maintenance': 'maintenance-synthetic.json'}
        existing = {(item['category'], item['sha256']) for item in store.list_incident_documents(case_id)}
        for category, filename in fixtures.items():
            payload = (fixture_dir / filename).read_bytes()
            key = (category, sha256(payload).hexdigest())
            if key not in existing:
                store.add_incident_document(case_id, category, filename, payload,
                                            request.state.identity['username'] if settings.auth_enabled else 'test_operator')
                existing.add(key)
        return {'case': store.get(case_id), 'sources': case_sources(case_id)}

    @app.post('/cases/{case_id}/sources')
    async def add_case_source(case_id: str, request: Request, category: str = Form(...), file: UploadFile = File(...)):
        if file.content_type not in {'application/pdf', 'application/json', 'text/csv',
                                     'text/plain', 'application/octet-stream'}:
            raise HTTPException(415, 'Use a PDF, JSON, CSV, or text source file.')
        payload = await file.read(5 * 1024 * 1024 + 1)
        if not payload or len(payload) > 5 * 1024 * 1024:
            raise HTTPException(413, 'Source file must be 1 byte to 5 MB.')
        try:
            return store.add_incident_document(case_id, category, file.filename or 'source', payload,
                                               request.state.identity['username'] if settings.auth_enabled else 'test_operator')
        except Conflict:
            raise
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/cases/{case_id}/sources/{document_id}')
    def get_case_source(case_id: str, document_id: str):
        document = store.incident_document(case_id, document_id)
        return Response(content=document['payload'], media_type='application/octet-stream',
                        headers={'Content-Disposition': f'attachment; filename="{document_id}.source"',
                                 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store',
                                 'X-Content-SHA256': document['sha256']})

    @app.post('/cases/{case_id}/review')
    def review(case_id: str, body: ReviewRequest, request: Request):
        reviewer = request.state.identity['username'] if settings.auth_enabled else body.reviewer.strip()
        if len(reviewer) < 2 or len(body.note.strip()) < 5:
            raise HTTPException(422, 'Reviewer identity and decision note must contain meaningful text.')
        return workflow.review(case_id, expected_version=body.expected_version,
                               action=body.action, reviewer=reviewer, note=body.note.strip(),
                               verified_source_ids=body.verified_source_ids,
                               source_check_note=body.source_check_note.strip())

    @app.post('/cases/{case_id}/amend')
    async def amend(case_id: str, body: AmendmentRequest, request: Request):
        operator = request.state.identity['username'] if settings.auth_enabled else body.operator.strip()
        if len(operator) < 2 or len(body.note.strip()) < 5:
            raise HTTPException(422, 'Operator identity and correction note must contain meaningful text.')
        current = store.get(case_id)
        if current.source != 'manual' or current.state != CaseState.HUMAN_REVIEW:
            raise HTTPException(409, 'Only operator-entered cases awaiting review can be corrected.')
        validate_incident(current.contract_snapshot, body.incident)
        return await workflow.amend(case_id, expected_version=body.expected_version,
                                    incident=body.incident, operator=operator,
                                    note=body.note.strip())

    @app.get('/recovery-summary')
    def summary():
        return store.summary()

    @app.get('/cases/{case_id}')
    def case(case_id: str):
        return store.get(case_id)

    @app.get('/cases/{case_id}/evidence-graph')
    def graph(case_id: str):
        return store.get(case_id).evidence_graph

    @app.get('/cases/{case_id}/claim-package')
    def package(case_id: str):
        package = store.get(case_id).claim_package
        if not package:
            raise HTTPException(409, 'Claim package not available for this case')
        return package

    @app.post('/cases/{case_id}/submit')
    def submit(case_id: str):
        return workflow.submit(case_id)

    @app.post('/cases/{case_id}/simulate-dispute')
    def dispute(case_id: str):
        return workflow.dispute(case_id)

    @app.post('/cases/{case_id}/defend')
    async def defend(case_id: str):
        return await workflow.defend(case_id)

    @app.post('/cases/{case_id}/simulate-accept')
    def accept(case_id: str):
        return workflow.accept(case_id)

    @app.post('/cases/{case_id}/reconcile')
    def reconcile(case_id: str):
        return workflow.reconcile(case_id)

    @app.post('/cases/{case_id}/accept-and-verify', deprecated=True)
    def compatibility_verify(case_id: str):
        accepted = workflow.accept(case_id)
        return workflow.reconcile(case_id) if accepted.state == 'accepted' else accepted

    @app.post('/cases/{case_id}/run-loop')
    def auto(case_id: str):
        return workflow.enable_auto(case_id)

    @app.post('/cases/{case_id}/step')
    async def step(case_id: str):
        return await workflow.step(case_id)

    @app.post('/watcher/tick')
    async def tick():
        await workflow.tick()
        return store.summary()

    @app.post('/vendor/claims')
    def vendor_submit(body: VendorSubmission):
        case = workflow.submit(body.case_id)
        if not case.vendor_claim_id:
            raise HTTPException(409, case.human_review_reason)
        return store.vendor(case.vendor_claim_id)

    @app.get('/vendor/claims/{claim_id}')
    def vendor_get(claim_id: str):
        return store.vendor(claim_id)

    @app.post('/vendor/claims/{claim_id}/simulate-dispute')
    def vendor_dispute(claim_id: str):
        workflow.dispute(store.vendor(claim_id)['case_id'])
        return store.vendor(claim_id)

    @app.post('/vendor/claims/{claim_id}/defense')
    async def vendor_defense(claim_id: str):
        case = await workflow.defend(store.vendor(claim_id)['case_id'])
        if case.state == 'human_review':
            raise HTTPException(409, case.human_review_reason)
        return store.vendor(claim_id)

    @app.post('/vendor/claims/{claim_id}/simulate-accept')
    def vendor_accept(claim_id: str):
        case = workflow.accept(store.vendor(claim_id)['case_id'])
        if case.state == 'human_review':
            raise HTTPException(409, case.human_review_reason)
        return store.vendor(claim_id)

    @app.get('/vendor/claims/{claim_id}/credit-memo')
    def memo(claim_id: str):
        store.vendor(claim_id)
        return {'memo': store.memo(claim_id)}

    return app


app = create_app()

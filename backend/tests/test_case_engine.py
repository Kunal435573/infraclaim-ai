import pytest
from app.schemas import CaseState
from app.services.case_engine import CaseEngine
from app.services.repository import load_contract, load_incidents
from app.services.store import Store
from app.services.workflow import Workflow
from app.config import Settings


@pytest.mark.asyncio
async def test_full_primary_flow(tmp_path):
    engine = CaseEngine()
    case = await engine.investigate(load_contract(), load_incidents()[0])
    assert case.state == CaseState.CLAIM_READY
    assert case.amount_usd == 40000
    settings = Settings(database_path=str(tmp_path / 'cases.db'), credit_delay_seconds=0)
    store = Store(settings.database_path)
    store.create(case)
    flow = Workflow(store, engine, settings)
    flow.submit(case.id)
    flow.dispute(case.id)
    await flow.defend(case.id)
    flow.accept(case.id)
    case = flow.reconcile(case.id)
    assert case.state == CaseState.VERIFIED
    assert any("$40,000.00" in e.message for e in case.timeline)


@pytest.mark.asyncio
async def test_ambiguous_case_escalates():
    engine = CaseEngine()
    case = await engine.investigate(load_contract(), load_incidents()[1])
    assert case.state == CaseState.HUMAN_REVIEW
    assert case.confidence < 0.90
    assert case.human_review_reason

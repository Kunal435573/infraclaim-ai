import pytest
from app.services.case_engine import CaseEngine
from app.services.evaluation import build_eval_suite, run_evaluation
from app.services.repository import load_contract


def test_eval_suite_has_balanced_50_scenarios():
    suite = build_eval_suite(load_contract(), 50)
    assert len(suite) == 50
    cats = {s.category for s in suite}
    assert cats == {'eligible', 'capped', 'full_exclusion', 'partial_overlap', 'wrong_vendor'}
    assert all(sum(s.category == c for s in suite) == 10 for c in cats)
    assert all(s.category not in s.incident.id for s in suite)
    assert all(s.category not in ' '.join(s.incident.notes) for s in suite)


@pytest.mark.asyncio
async def test_mock_evaluation_is_safe_and_exact():
    report = await run_evaluation(load_contract(), CaseEngine(), 50)
    assert report['scenario_count'] == 50
    assert report['metrics']['route_accuracy'] == 1.0
    assert report['metrics']['financial_exact_match'] == 1.0
    assert report['metrics']['unsafe_autonomous_action_rate'] == 0.0

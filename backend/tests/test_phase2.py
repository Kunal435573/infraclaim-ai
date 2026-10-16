import pytest
from app.schemas import CaseState
from app.services.case_engine import CaseEngine
from app.services.contract_ingestion import ContractIngestor, load_demo_contract_pdf
from app.services.repository import load_contract, load_incidents


@pytest.mark.asyncio
async def test_demo_pdf_contract_ingestion_extracts_section_74():
    result = await ContractIngestor().ingest_pdf(
        load_demo_contract_pdf(),
        "ThermaCore_Master_Service_Agreement_2026.pdf",
    )
    assert result.pages == 3
    assert result.contract.customer == "NovaCompute"
    assert result.contract.vendor == "ThermaCore"
    assert result.contract.sla.source_page == 2
    assert result.contract.sla.source_section == "Section 7.4"
    assert result.contract.sla.rate_per_eligible_hour_usd == 10000
    assert result.contract.sla.cap_usd == 50000
    assert result.contract.sla.claim_window_days == 30
    assert "planned maintenance" in result.contract.sla.exclusions


@pytest.mark.asyncio
async def test_primary_case_has_structured_reasoning_graph_and_claim_package():
    case = await CaseEngine().investigate(load_contract(), load_incidents()[0])
    assert case.state == CaseState.CLAIM_READY
    assert case.reasoning is not None
    assert case.reasoning.decision == "supported"
    assert case.evidence_graph is not None
    assert any(node.id == "contract_clause" for node in case.evidence_graph.nodes)
    assert any(edge.relation == "defines_remedy" for edge in case.evidence_graph.edges)
    assert case.claim_package is not None
    assert case.claim_package.amount_usd == 40000
    assert case.claim_package.clause_ids == ["sla.cooling.7.4"]
    assert case.claim_package.approval_required is False


@pytest.mark.asyncio
async def test_ambiguous_overlap_is_captured_as_contradiction_and_escalated():
    case = await CaseEngine().investigate(load_contract(), load_incidents()[1])
    assert case.state == CaseState.HUMAN_REVIEW
    assert case.reasoning is not None
    assert case.reasoning.contradictions
    assert case.claim_package is None
    assert "Contradictory evidence" in case.human_review_reason

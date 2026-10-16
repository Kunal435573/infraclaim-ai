from app.schemas import EvidenceEdge, EvidenceGraph, EvidenceNode, EvidenceItem, InfrastructureIncident, VendorContract


def build_evidence_graph(contract: VendorContract, incident: InfrastructureIncident, evidence: list[EvidenceItem]) -> EvidenceGraph:
    nodes = [
        EvidenceNode(
            id="contract_clause",
            kind="contract_clause",
            label=f"{contract.sla.source_section or contract.sla.id}: {contract.sla.title}",
            metadata={"page": contract.sla.source_page, "clause_id": contract.sla.id},
        ),
        EvidenceNode(
            id="incident",
            kind="incident",
            label=f"{incident.severity.title()} incident · {incident.id}",
            metadata={"start": incident.start.isoformat(), "end": incident.end.isoformat()},
        ),
        EvidenceNode(
            id="entitlement",
            kind="commercial_outcome",
            label="Contractual entitlement",
            status="derived",
        ),
    ]
    edges = [
        EvidenceEdge(source="incident", target="contract_clause", relation="governed_by"),
        EvidenceEdge(source="contract_clause", target="entitlement", relation="defines_remedy"),
    ]

    for item in evidence:
        if item.type == "contract_clause":
            continue
        status = "potential_conflict" if item.type == "maintenance" else "supporting"
        node_id = item.id
        nodes.append(EvidenceNode(
            id=node_id,
            kind=item.type,
            label=item.summary,
            status=status,
            metadata={
                "source": item.source,
                "timestamp": item.timestamp.isoformat() if item.timestamp else None,
                "value": item.value,
            },
        ))
        edges.append(EvidenceEdge(source=node_id, target="incident", relation="supports_or_contextualizes"))

    return EvidenceGraph(nodes=nodes, edges=edges)


def find_contradictions(incident: InfrastructureIncident) -> list[str]:
    contradictions: list[str] = []
    for window in incident.maintenance_windows:
        overlap_start = max(incident.start, window.start)
        overlap_end = min(incident.end, window.end)
        if overlap_end > overlap_start:
            contradictions.append(
                f"Maintenance window overlaps incident from {overlap_start.isoformat()} to {overlap_end.isoformat()}."
            )
    for note in incident.notes:
        if "ambiguous" in note.lower() or "conflict" in note.lower():
            contradictions.append(note)
    return contradictions

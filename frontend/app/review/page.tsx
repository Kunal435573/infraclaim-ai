'use client'

import { useEffect, useMemo, useState } from 'react'
import AppShell from '../AppShell'
import CorrectionForm from './CorrectionForm'

type Case = {
  id: string; incident_id: string; version: number; source: string; state: string;
  amount_usd: number; confidence: number; human_review_reason?: string | null;
  contract_id: string;
  contract_snapshot?: { customer: string; vendor: string; source_document_id?: string;
    sla: { title: string; source_section?: string; source_quote?: string } };
  incident_snapshot?: { id: string; start: string; end: string; service: string; vendor: string;
    severity: string; ticket_opened_at: string; vendor_acknowledged_at: string;
    telemetry: Record<string, string | number>;
    maintenance_windows: { start: string; end: string; description: string }[]; notes: string[] };
  evidence: { id: string; type: string; source: string; summary: string }[];
  reasoning?: { decision: string; summary: string; citations: string[]; contradictions: string[];
    inference?: { execution: string; status: string } };
  reviews: { action: string; reviewer: string; note: string; at: string;
    source_check_note?: string; verified_sources?: { id: string; sha256: string; category: string }[] }[];
  amendments?: { at: string; operator: string; note: string; reassessment: string }[];
}
type SourceDoc = { id: string; category: 'ticket' | 'telemetry' | 'maintenance'; filename: string;
  sha256: string; uploaded_at: string; uploader: string;
  analysis?: { recognized: boolean; findings: string[] } }
const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/api${path}`, init)
  const value = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `Request failed (${response.status})`)
  return value
}

export default function Review() {
  const [cases, setCases] = useState<Case[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [identity, setIdentity] = useState<{ username: string; role: string } | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [sources, setSources] = useState<SourceDoc[]>([])
  const [verifiedIds, setVerifiedIds] = useState<string[]>([])
  const [sourceCheckNote, setSourceCheckNote] = useState('')
  const [sourceCategory, setSourceCategory] = useState<SourceDoc['category']>('ticket')
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const queue = useMemo(() => cases.filter(item => item.state === 'human_review'), [cases])
  const selected = cases.find(item => item.id === selectedId)
  async function refresh() {
    try {
      const result: Case[] = await request('/cases')
      setCases(result)
      const requested = new URLSearchParams(window.location.search).get('case')
      setSelectedId(current => current || (requested && result.some(item => item.id === requested) ? requested : '') || result.find(item => item.state === 'human_review')?.id || '')
      setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Cases could not be loaded.') }
  }
  useEffect(() => { refresh(); request('/auth/me').then(setIdentity).catch(() => {}) }, [])
  useEffect(() => {
    setSources([]); setVerifiedIds([]); setSourceCheckNote('')
    if (selectedId) request(`/cases/${selectedId}/sources`).then(setSources).catch(() => {})
  }, [selectedId, selected?.version])
  async function uploadSource() {
    if (!selected || !sourceFile) return
    setBusy(true); setError(''); setMessage('')
    try {
      const body = new FormData(); body.append('category', sourceCategory); body.append('file', sourceFile)
      const result = await request(`/cases/${selected.id}/sources`, { method: 'POST', body })
      setCases(current => current.map(item => item.id === result.case.id ? result.case : item))
      setSources(await request(`/cases/${selected.id}/sources`)); setSourceFile(null)
      setVerifiedIds([]); setSourceCheckNote('')
      setMessage('Source stored with checksum. A separate reviewer must compare it with the entered incident.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Source could not be uploaded.') }
    finally { setBusy(false) }
  }
  async function attachPilotSources() {
    if (!selected) return
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await request(`/cases/${selected.id}/sources/pilot-fixtures`, { method: 'POST' })
      setCases(current => current.map(item => item.id === result.case.id ? result.case : item))
      setSources(result.sources); setVerifiedIds([]); setSourceCheckNote('')
      setMessage('Three correctly labelled pilot files are attached. Compare their contents with the entered incident before approval.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Pilot sources could not be attached.') }
    finally { setBusy(false) }
  }
  const sourceReady = ['ticket', 'telemetry', 'maintenance'].every(category =>
    sources.some(item => item.category === category && verifiedIds.includes(item.id) && !item.analysis?.findings.length)) && sourceCheckNote.trim().length >= 20
  async function decide(action: 'approve_simulation' | 'request_information' | 'reject') {
    if (!selected) return
    setBusy(true); setError(''); setMessage('')
    try {
      const result: Case = await request(`/cases/${selected.id}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: selected.version, action, note: note.trim(),
          verified_source_ids: action === 'approve_simulation' ? verifiedIds : [],
          source_check_note: action === 'approve_simulation' ? sourceCheckNote.trim() : '' }),
      })
      setCases(current => current.map(item => item.id === result.id ? result : item))
      setMessage(action === 'approve_simulation' ? 'Approved for simulated submission. No vendor message was sent.' :
        action === 'reject' ? 'Claim rejected and closed.' : 'Request recorded; case remains in review.')
      setNote('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Decision could not be recorded.') }
    finally { setBusy(false) }
  }
  return <AppShell active="review" eyebrow="HUMAN DECISIONS" title="Review queue"
    description="Verify the contract, entered evidence, and model assessment. Approval only enables a simulated claim after policy checks pass."
    actions={<a className="uiButton secondary" href="/intake">Open a case</a>}>
    {error && <div className="uiAlert error" role="alert">{error}</div>}{message && <div className="uiAlert success" role="status">{message}</div>}
    <div className="reviewLayout"><aside className="uiCard reviewList"><div className="cardHeading"><div><span className="sectionKicker">01 / QUEUE</span><h2>{queue.length} awaiting review</h2></div><button className="uiButton text" onClick={refresh}>Refresh</button></div>
      {queue.length ? queue.map(item => <button key={item.id} className={`caseRow ${selectedId === item.id ? 'selected' : ''}`} onClick={() => { setSelectedId(item.id); setError(''); setMessage('') }}><span>{item.incident_id}</span><b>{money(item.amount_usd)}</b><small>{item.source === 'manual' ? 'Operator entered' : 'Sample case'}</small></button>) : <p className="muted">No open reviews. <a href="/intake">Open a case</a> to create one.</p>}
      {selected && selected.state !== 'human_review' && <button className="caseRow selected" onClick={() => setSelectedId(selected.id)}><span>{selected.incident_id}</span><b>{selected.state.replaceAll('_', ' ')}</b></button>}
    </aside>
    <section className="uiCard reviewDetail">{selected ? <>
      <div className="detailTop"><div><span className="sectionKicker">02 / DECISION FILE · {selected.source === 'manual' ? 'OPERATOR ENTRY' : 'SYNTHETIC SAMPLE'}</span><h2>{selected.incident_id}</h2><p>{selected.contract_snapshot?.customer} → {selected.contract_snapshot?.vendor}</p></div><span className={`stateTag state-${selected.state}`}>{selected.state.replaceAll('_', ' ')}</span></div>
      <div className="reviewStats"><div><span>Estimated credit</span><strong>{money(selected.amount_usd)}</strong></div><div><span>Model assessment</span><strong>{selected.reasoning?.decision?.replaceAll('_', ' ') || 'Unavailable'}</strong></div><div><span>Model score · uncalibrated</span><strong>{Math.round(selected.confidence * 100)}%</strong></div></div>
      {selected.state === 'claim_ready' && <div className="reviewNext"><span>Review complete. This claim is ready for simulated submission.</span><a className="uiButton" href={`/?case=${encodeURIComponent(selected.id)}`}>Continue in overview <span aria-hidden="true">→</span></a></div>}
      <div className="reviewBlock"><h3>Why it needs review</h3><p>{selected.human_review_reason || 'Review has been completed.'}</p><p className="muted">{selected.reasoning?.summary} {selected.reasoning?.inference && `(${selected.reasoning.inference.execution}; ${selected.reasoning.inference.status})`}</p></div>
      <div className="reviewBlock"><h3>Contract and incident</h3><p>{selected.contract_snapshot?.customer} → {selected.contract_snapshot?.vendor} · {selected.contract_snapshot?.sla.title}</p><p className="muted">{selected.incident_snapshot?.service} · {selected.incident_snapshot?.start} to {selected.incident_snapshot?.end}</p><blockquote>{selected.contract_snapshot?.sla.source_quote || 'No source excerpt stored.'}</blockquote>{selected.contract_snapshot?.source_document_id && <a className="sourceLink" href={`/api/contracts/${encodeURIComponent(selected.contract_id)}/source`}>Download original contract PDF <span aria-hidden="true">↗</span></a>}{!selected.contract_snapshot?.source_document_id && selected.source === 'manual' && <p className="muted">Original contract PDF was not uploaded for this case.</p>}</div>
      <div className="reviewBlock"><h3>Evidence to check</h3><div className="evidenceList">{selected.evidence.map(item => <div key={item.id}><b>{item.id}</b><span>{item.summary}</span><small>{item.source}</small></div>)}</div><p className="muted">Cited IDs: {selected.reasoning?.citations?.join(', ') || 'none'}</p>{!!selected.reasoning?.contradictions?.length && <div className="warning">{selected.reasoning.contradictions.join(' · ')}</div>}</div>
      {selected.source === 'manual' && <div className="reviewBlock"><h3>Incident source files</h3><p className="muted">Files are uploaded by an operator and stored with a checksum. Uploading alone does not prove they came from an independent system.</p>
        {sources.length ? <div className="sourceList">{sources.map(item => <div className="sourceRow" key={item.id}><div><strong>{item.category} · {item.filename}</strong><small>Uploaded by {item.uploader} · SHA-256 {item.sha256.slice(0, 16)}…</small><small className={item.analysis?.findings.length ? 'sourceMismatch' : ''}>{item.analysis?.findings.length ? item.analysis.findings.join(' ') : item.analysis?.recognized ? 'Sample file matches the entered incident.' : 'Origin and contents require manual comparison.'}</small></div><a className="sourceLink" href={`/api/cases/${selected.id}/sources/${item.id}`}>Download</a>{selected.state === 'human_review' && ['reviewer', 'admin'].includes(identity?.role || '') && <label><input type="checkbox" disabled={item.uploader === identity?.username || !!item.analysis?.findings.length} checked={verifiedIds.includes(item.id)} onChange={event => setVerifiedIds(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))}/> Checked</label>}</div>)}</div> : <p>No incident source files attached.</p>}
        {selected.state === 'human_review' && ['operator', 'admin'].includes(identity?.role || '') && <div className="sourceUpload"><label className="field">Source type<select value={sourceCategory} onChange={event => setSourceCategory(event.target.value as SourceDoc['category'])}><option value="ticket">Ticket</option><option value="telemetry">Telemetry</option><option value="maintenance">Maintenance calendar</option></select></label><label className="field">PDF, CSV, JSON or text (up to 5 MB)<input type="file" accept=".pdf,.csv,.json,.txt" onChange={event => setSourceFile(event.target.files?.[0] || null)}/></label><button className="uiButton secondary" disabled={busy || !sourceFile} onClick={uploadSource}>Attach source</button></div>}
        {selected.state === 'human_review' && selected.incident_id === 'pilot_manual_001' && ['operator', 'admin'].includes(identity?.role || '') && <div className="pilotSourceAction"><p className="muted">Using the bundled synthetic pilot case? Attach its three sample exports with the correct source types in one step.</p><button className="uiButton secondary" disabled={busy} onClick={attachPilotSources}>Attach pilot sample files</button></div>}
        {selected.state === 'human_review' && ['reviewer', 'admin'].includes(identity?.role || '') && <label className="field">How did you check the selected files against the source records?<textarea rows={3} value={sourceCheckNote} onChange={event => setSourceCheckNote(event.target.value)} placeholder="Name the system or record you compared, and any mismatch."/></label>}
      </div>}
      {selected.source === 'manual' && selected.state === 'human_review' && ['operator', 'admin'].includes(identity?.role || '') && <div className="reviewBlock"><CorrectionForm caseData={selected} onSaved={result => { setCases(current => current.map(item => item.id === result.id ? result : item)); setVerifiedIds([]); setSourceCheckNote(''); setMessage('Correction saved and reassessed. Sources must be checked again before a new decision.'); setError('') }}/></div>}
      {!!selected.amendments?.length && <div className="reviewBlock"><h3>Correction history</h3>{selected.amendments.map((item, index) => <p key={index}><b>{item.operator}</b> corrected the incident · {item.note} · Reassessment: {item.reassessment.replaceAll('_', ' ')}</p>)}</div>}
      {!!selected.reviews?.length && <div className="reviewBlock"><h3>Review history</h3>{selected.reviews.map((item, index) => <p key={index}><b>{item.action.replaceAll('_', ' ')}</b> by {item.reviewer} · {item.note}{item.source_check_note && <> · Source check: {item.source_check_note} ({item.verified_sources?.length || 0} files)</>}</p>)}</div>}
      {selected.state === 'human_review' && ['reviewer', 'admin'].includes(identity?.role || '') && <div className="reviewBlock decisionBox"><span className="sectionKicker">03 / YOUR DECISION</span><h3>Record a decision</h3><p className="muted">This decision will be recorded as {identity?.username}. Approval cannot override missing evidence, contradictions, or a failed model assessment. Manual cases also need checked ticket, telemetry, and maintenance sources.</p><label className="field">Reason or next information needed<textarea rows={3} value={note} onChange={e => setNote(e.target.value)} placeholder="What did you verify or what is missing?"/></label><div className="decisionActions"><button className="uiButton" disabled={busy || note.trim().length < 5 || (selected.source === 'manual' && !sourceReady)} onClick={() => decide('approve_simulation')}>{busy ? 'Recording…' : 'Approve for simulation'}</button><button className="uiButton secondary" disabled={busy || note.trim().length < 5} onClick={() => decide('request_information')}>Request information</button><button className="uiButton text dangerText" disabled={busy || note.trim().length < 5} onClick={() => decide('reject')}>Reject claim</button></div></div>}
    </> : <div className="emptyState"><h3>Select a case</h3><p>Cases awaiting a decision will appear here.</p></div>}</section></div>
  </AppShell>
}

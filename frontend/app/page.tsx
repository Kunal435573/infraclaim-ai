'use client'

import { useEffect, useMemo, useState } from 'react'
import AppShell from './AppShell'

type Event = { at: string; state: string; message: string }
type Evidence = { id: string; type?: string; source?: string; summary?: string }
type Decision = { action: string; allowed: boolean; reasons: string[] }
type Case = {
  id: string; incident_id: string; source?: string; state: string; version: number;
  amount_usd: number; confidence: number; auto_run: boolean; review_approved?: boolean;
  human_review_reason?: string | null; timeline: Event[]; evidence?: Evidence[];
  reasoning?: { summary: string; citations: string[]; contradictions: string[];
    inference?: { execution: string; status: string; model?: string } } | null;
  policy_decisions: Decision[];
  contract_snapshot?: { customer: string; vendor: string; sla: { title: string; source_section?: string; source_quote?: string } };
  claim_package?: { factual_basis: string } | null;
  counter_investigation?: { summary: string } | null;
  reconciliation?: { matched: boolean; memo: { id: string; amount_cents: number; status: string } } | null;
}
type Runtime = { mode: string; configured: boolean; vendor_mode: string }
const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value)
const label = (value?: string) => value?.replaceAll('_', ' ') || 'No case selected'
const finished = new Set(['verified', 'closed'])
async function request(path: string, method = 'GET') {
  const response = await fetch('/api' + path, { method, cache: 'no-store' })
  const value = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `Request failed (${response.status})`)
  return value
}

export default function Overview() {
  const [cases, setCases] = useState<Case[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [verified, setVerified] = useState(0)
  const [runtime, setRuntime] = useState<Runtime | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [view, setView] = useState<'all' | 'review'>('all')
  const selected = useMemo(() => cases.find(item => item.id === selectedId) || null, [cases, selectedId])
  const reviewCount = cases.filter(item => item.state === 'human_review').length
  const listed = view === 'review' ? cases.filter(item => item.state === 'human_review') : cases

  useEffect(() => {
    let active = true
    async function refresh() {
      try {
        const [all, recovery, status] = await Promise.all([
          request('/cases'), request('/recovery-summary'), request('/ai/runtime'),
        ])
        if (!active) return
        setCases(all)
        setVerified(recovery.verified_amount_usd || 0)
        setRuntime(status)
        setSelectedId(current => {
          if (current && all.some((item: Case) => item.id === current)) return current
          const requested = new URLSearchParams(window.location.search).get('case')
          return requested && all.some((item: Case) => item.id === requested) ? requested : all[0]?.id || ''
        })
      } catch { if (active) setRuntime(null) }
    }
    refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  async function runSample(incident = 'inc_cooling_001') {
    setBusy(true); setError('')
    try {
      await request('/contracts/demo/ingest')
      const created: Case = await request(`/demo/investigate/${incident}`, 'POST')
      const result: Case = incident.includes('ambiguous') || created.state !== 'claim_ready'
        ? created : await request(`/cases/${created.id}/run-loop`, 'POST')
      setCases(current => [result, ...current.filter(item => item.id !== result.id)])
      setSelectedId(result.id)
      setView('all')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The sample could not run.') }
    finally { setBusy(false) }
  }
  async function advance(path: string) {
    if (!selected) return
    setBusy(true); setError('')
    try {
      const result: Case = await request(`/cases/${selected.id}${path}`, 'POST')
      setCases(current => current.map(item => item.id === result.id ? result : item))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The action could not complete.') }
    finally { setBusy(false) }
  }
  const nextActions: { state: string[]; label: string; path: string; secondary?: boolean }[] = [
    { state: ['claim_ready'], label: 'Submit simulated claim', path: '/submit' },
    { state: ['submitted'], label: 'Simulate vendor dispute', path: '/simulate-dispute', secondary: true },
    { state: ['disputed'], label: 'Defend with evidence', path: '/defend' },
    { state: ['submitted', 'defended'], label: 'Simulate acceptance', path: '/simulate-accept', secondary: true },
    { state: ['accepted'], label: 'Reconcile credit', path: '/reconcile' },
  ]

  return <AppShell active="overview" eyebrow="WORKSPACE OVERVIEW" title="Claims operations"
    description="InfraClaim helps data-center operators recover SLA service credits when a vendor misses a contract promise. Each case links the incident, contract, evidence, and proposed credit."
    actions={<a className="uiButton" href="/intake">Open a case <span aria-hidden="true">→</span></a>}>
    {error && <div className="uiAlert error" role="alert">{error}</div>}
    <div className="overviewMetrics" aria-label="Workspace metrics">
      <div><span>Cases on record</span><strong>{cases.length}</strong><small>Saved in this workspace</small></div>
      <div><span>Awaiting review</span><strong>{reviewCount}</strong><small>Human decision required</small></div>
      <div><span>Simulated credits verified</span><strong>{money(verified)}</strong><small>No real funds moved</small></div>
      <div><span>Model connection</span><strong className="metricStatus">{runtime ? runtime.mode === 'mock' ? 'Mock mode' : runtime.configured ? 'Configured' : 'Key missing' : 'Offline'}</strong><small>{runtime?.vendor_mode === 'simulated' ? 'Vendor simulator active' : 'Check service status'}</small></div>
    </div>

    <div className="overviewGrid">
      <section className="uiCard caseList" aria-label="Cases">
        <div className="cardHeading"><div><span className="sectionKicker">01 / CASES</span><h2>Case register</h2></div><span className="countPill">{cases.length}</span></div>
        <div className="segmented" aria-label="Filter cases"><button aria-pressed={view === 'all'} onClick={() => setView('all')}>All cases</button><button aria-pressed={view === 'review'} onClick={() => setView('review')}>Needs review <span>{reviewCount}</span></button></div>
        <div className="caseItems">{listed.length ? listed.map(item => <button key={item.id} className={selectedId === item.id ? 'caseItem isSelected' : 'caseItem'} onClick={() => setSelectedId(item.id)} aria-pressed={selectedId === item.id}>
          <span className="caseItemTop"><strong>{item.incident_id}</strong><span className={`stateTag state-${item.state}`}>{label(item.state)}</span></span>
          <span className="caseItemBottom"><span>{item.source === 'manual' ? 'Operator entry' : 'Sample case'}</span><b>{money(item.amount_usd)}</b></span>
        </button>) : <div className="emptyList"><strong>{view === 'review' ? 'No cases need review' : 'No cases yet'}</strong><p>{view === 'review' ? 'When a decision needs a person, it will appear here.' : 'Start with a contract and incident, or run a sample workflow.'}</p></div>}</div>
      </section>

      <section className="uiCard caseDetail" aria-label="Selected case">
        {selected ? <>
          <div className="detailTop"><div><span className="sectionKicker">02 / CASE FILE</span><h2>{selected.incident_id}</h2><p>{selected.contract_snapshot?.customer || 'Sample customer'} <span aria-hidden="true">→</span> {selected.contract_snapshot?.vendor || 'Sample vendor'}</p></div><span className={`stateTag state-${selected.state}`}>{label(selected.state)}</span></div>
          <div className="caseSummary"><div><span>Proposed credit</span><strong>{money(selected.amount_usd)}</strong></div><div><span>Model score · uncalibrated</span><strong>{Math.round(selected.confidence * 100)}%</strong></div><div><span>Source</span><strong>{selected.source === 'manual' ? 'Operator entered' : 'Synthetic demo'}</strong></div></div>
          {selected.state === 'human_review' && <div className="reviewCallout"><div><strong>Decision required</strong><p>{selected.human_review_reason || 'This case needs a human reviewer.'}</p></div><a className="uiButton" href={`/review?case=${encodeURIComponent(selected.id)}`}>Review case <span aria-hidden="true">→</span></a></div>}
          <div className="detailSection"><div className="detailSectionHead"><h3>Assessment</h3><span>{selected.reasoning?.inference?.execution || 'Not available'} · {selected.reasoning?.inference?.status || 'Unknown'}</span></div><p>{selected.reasoning?.summary || 'Investigation has not produced an assessment yet.'}</p>{!!selected.reasoning?.contradictions?.length && <div className="inlineWarning"><strong>Conflicting evidence</strong>{selected.reasoning.contradictions.map((value, index) => <p key={index}>{value}</p>)}</div>}</div>
          <div className="detailTwo"><div className="detailSection"><h3>Evidence</h3><p>{selected.evidence?.length || 0} recorded sources · {selected.reasoning?.citations?.length || 0} cited</p><ul className="compactList">{selected.evidence?.slice(0, 4).map(item => <li key={item.id}><b>{item.type?.replaceAll('_', ' ') || item.id}</b><span>{item.source === 'operator_entry' ? 'Operator supplied' : item.source || 'Recorded'}</span></li>)}</ul></div><div className="detailSection"><h3>Policy checks</h3><p>{selected.policy_decisions?.length || 0} recorded decisions</p><ul className="compactList">{selected.policy_decisions?.slice(-4).map((decision, index) => <li key={index}><b>{label(decision.action)}</b><span>{decision.allowed ? 'Allowed' : 'Blocked'}</span></li>)}</ul></div></div>
          <div className="detailSection"><h3>Case timeline</h3><ol className="caseTimeline">{selected.timeline?.slice(-5).reverse().map((event, index) => <li key={index}><time>{new Date(event.at).toLocaleString()}</time><strong>{label(event.state)}</strong><p>{event.message}</p></li>)}</ol></div>
          {selected.reconciliation && <div className="reconcileBox"><strong>{selected.reconciliation.matched ? 'Simulated credit matched' : 'Credit mismatch'}</strong><span>{selected.reconciliation.memo.id} · {money(selected.reconciliation.memo.amount_cents / 100)}</span></div>}
          {!finished.has(selected.state) && selected.state !== 'human_review' && !selected.auto_run && <div className="detailActions"><span>SIMULATION CONTROLS</span>{nextActions.filter(action => action.state.includes(selected.state)).map(action => <button key={action.path} className={action.secondary ? 'uiButton secondary' : 'uiButton'} disabled={busy} onClick={() => advance(action.path)}>{busy ? 'Working…' : action.label}</button>)}{selected.state === 'claim_ready' && <button className="uiButton secondary" disabled={busy} onClick={() => advance('/run-loop')}>Run remaining workflow</button>}</div>}
        </> : <div className="detailEmpty"><span className="sectionKicker">02 / CASE FILE</span><h2>Choose a case</h2><p>Open an existing case from the register, or start a new one to see its evidence and decisions here.</p><a className="uiButton" href="/intake">Open a case</a></div>}
      </section>
    </div>
    <section className="sampleStrip"><div><span className="sectionKicker">EXPLORE THE WORKFLOW</span><h2>Try a synthetic incident</h2><p>See a full claim or an ambiguous case that stops for human review. Both use simulated vendor and credit actions.</p></div><div><button className="uiButton secondary" disabled={busy} onClick={() => runSample()}>{busy ? 'Running…' : 'Run eligible sample'}</button><button className="uiButton text" disabled={busy} onClick={() => runSample('inc_cooling_ambiguous')}>Run ambiguous sample <span aria-hidden="true">→</span></button></div></section>
  </AppShell>
}

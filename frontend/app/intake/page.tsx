'use client'

import { useEffect, useState } from 'react'
import AppShell from '../AppShell'

type Contract = {
  id: string; customer: string; vendor: string; effective_date: string;
  source_filename?: string; source_text_sha256?: string; source_document_id?: string; source_file_sha256?: string;
  sla: { id: string; title: string; service: string; response_minutes: number;
    repair_minutes: number; rate_per_eligible_hour_usd: number; cap_usd: number;
    claim_window_days: number; exclusions: string[]; source_section: string;
    source_quote: string; source_page?: number }
}
const emptyContract: Contract = {
  id: '', customer: '', vendor: '', effective_date: '',
  sla: { id: '', title: '', service: 'critical_cooling_loop_b', response_minutes: 15,
    repair_minutes: 120, rate_per_eligible_hour_usd: 10000, cap_usd: 50000,
    claim_window_days: 30, exclusions: ['planned maintenance'], source_section: '', source_quote: '' },
}
async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/api${path}`, init)
  const value = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `Request failed (${response.status})`)
  return value
}
function utc(value: string) {
  const date = new Date(value)
  if (!value || Number.isNaN(date.valueOf())) throw new Error('Enter all required dates and times.')
  return date.toISOString()
}

export default function Intake() {
  const [contracts, setContracts] = useState<Contract[]>([])
  const [contract, setContract] = useState<Contract>(emptyContract)
  const [savedId, setSavedId] = useState('')
  const [preview, setPreview] = useState('')
  const [incident, setIncident] = useState({ id: '', start: '', end: '', ticket: '', ack: '',
    severity: 'critical', pump: '', pressure: '', note: '' })
  const [maintenance, setMaintenance] = useState({ mode: '', start: '', end: '', description: '' })
  const [created, setCreated] = useState<{ id: string; state: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [stage, setStage] = useState<1 | 2>(1)
  useEffect(() => { request('/contracts').then(setContracts).catch(() => {}) }, [])
  const edit = (name: keyof Contract, value: string) => {
    setContract(current => ({ ...current, [name]: value })); setSavedId('')
  }
  const editSla = (name: keyof Contract['sla'], value: string | number) => {
    setContract(current => ({ ...current, sla: { ...current.sla, [name]: value } })); setSavedId('')
  }
  async function upload(file?: File) {
    if (!file) return
    setBusy(true); setError(''); setPreview('')
    try {
      const body = new FormData(); body.append('file', file)
      const parsed = await request('/contracts/ingest', { method: 'POST', body })
      setContract(parsed.contract); setSavedId(''); setPreview(parsed.extracted_text_preview)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'PDF could not be read.') }
    finally { setBusy(false) }
  }
  async function saveContract() {
    setBusy(true); setError('')
    try {
      const payload = { ...contract, effective_date: utc(`${contract.effective_date.slice(0, 10)}T00:00:00Z`),
        source_filename: contract.source_filename || 'operator_entry' }
      const saved = await request('/contracts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      setContracts(current => [saved, ...current]); setContract(saved); setSavedId(saved.id); setStage(2)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Contract could not be saved.') }
    finally { setBusy(false) }
  }
  async function createCase() {
    setBusy(true); setError(''); setCreated(null)
    try {
      if (!savedId) throw new Error('Save or select a contract first.')
      if (!maintenance.mode) throw new Error('Choose a maintenance status.')
      if (!incident.pump.trim()) throw new Error('Enter the observed pump state.')
      const windows = maintenance.mode === 'recorded' ? [{ start: utc(maintenance.start), end: utc(maintenance.end),
        description: maintenance.description.trim() }] : []
      const payload = { contract_id: savedId, incident: {
        id: incident.id.trim() || `operator_${crypto.randomUUID()}`, service: contract.sla.service,
        vendor: contract.vendor, start: utc(incident.start), end: utc(incident.end),
        ticket_opened_at: utc(incident.ticket), vendor_acknowledged_at: utc(incident.ack),
        severity: incident.severity, telemetry: { pump_state: incident.pump.trim(),
          ...(incident.pressure ? { coolant_pressure_bar: Number(incident.pressure) } : {}) },
        maintenance_windows: windows, notes: incident.note.trim() ? [incident.note.trim()] : [],
      } }
      const result = await request('/cases/intake', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      setCreated({ id: result.id, state: result.state })
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Case could not be created.') }
    finally { setBusy(false) }
  }
  return <AppShell active="intake" eyebrow="NEW CLAIM / TWO STEPS" title="Open a case"
    description="Start with the contract, then enter the incident. A person reviews every operator-entered case before simulated submission."
    actions={<a className="uiButton secondary" href="/review">Go to review queue</a>}>
    <div className="formSteps" aria-label="Case intake progress"><button className={stage === 1 ? 'current' : ''} aria-current={stage === 1 ? 'step' : undefined} onClick={() => setStage(1)}><span>1</span> Contract terms</button><span className="stepConnector"/><button className={stage === 2 ? 'current' : ''} aria-current={stage === 2 ? 'step' : undefined} disabled={!savedId} onClick={() => setStage(2)}><span>2</span> Incident details</button></div>
    {error && <div className="uiAlert error" role="alert">{error}</div>}
    <section className="intakeFlow">
      {stage === 1 && <article className="uiCard intakeCard"><div className="flowSectionHead"><span className="sectionKicker">STEP 01 / 02</span><h2>Define the contract</h2><p>We use these terms to calculate a potential service credit. The pilot supports hourly cooling credits with a planned-maintenance exclusion.</p></div>
        <p className="muted">Upload a supported cooling-SLA PDF or enter terms from the source clause. Check every field before saving. Uploaded originals are linked to the saved contract in this local pilot.</p>
        <label className="field">Saved contract<select value={savedId} onChange={event => { const id = event.target.value; setSavedId(id); if (id) { setContract(contracts.find(item => item.id === id) || emptyContract); setStage(2) } else setContract(emptyContract) }}><option value="">Create a new contract</option>{contracts.map(item => <option key={item.id} value={item.id}>{item.customer} / {item.vendor} — {item.id}</option>)}</select></label>
        <label className="field">Preview PDF<input type="file" accept="application/pdf" disabled={busy} onChange={event => upload(event.target.files?.[0])}/></label>
        {contract.source_document_id && <div className="sourceNotice">{savedId ? <>Original PDF archived. <a href={`/api/contracts/${encodeURIComponent(savedId)}/source`}>Download source PDF</a></> : 'PDF uploaded. Save the contract to link its original source.'}</div>}
        {preview && <details><summary>Extracted text preview</summary><pre className="sourcePreview">{preview}</pre></details>}
        <div className="fieldsTwo">
          <label className="field">Contract ID<input value={contract.id} onChange={e => edit('id', e.target.value)} placeholder="contract_2026_01"/></label>
          <label className="field">Effective date<input type="date" value={contract.effective_date.slice(0, 10)} onChange={e => edit('effective_date', e.target.value)}/></label>
          <label className="field">Customer<input value={contract.customer} onChange={e => edit('customer', e.target.value)}/></label>
          <label className="field">Vendor<input value={contract.vendor} onChange={e => edit('vendor', e.target.value)}/></label>
          <label className="field">SLA ID<input value={contract.sla.id} onChange={e => editSla('id', e.target.value)}/></label>
          <label className="field">Service ID<input value={contract.sla.service} onChange={e => editSla('service', e.target.value)}/></label>
          <label className="field">SLA title<input value={contract.sla.title} onChange={e => editSla('title', e.target.value)}/></label>
          <label className="field">Source section<input value={contract.sla.source_section} onChange={e => editSla('source_section', e.target.value)} placeholder="Section 7.4"/></label>
          <label className="field">Response minutes<input type="number" min="1" value={contract.sla.response_minutes} onChange={e => editSla('response_minutes', Number(e.target.value))}/></label>
          <label className="field">Repair minutes<input type="number" min="1" value={contract.sla.repair_minutes} onChange={e => editSla('repair_minutes', Number(e.target.value))}/></label>
          <label className="field">Credit per eligible hour (USD)<input type="number" min="1" value={contract.sla.rate_per_eligible_hour_usd} onChange={e => editSla('rate_per_eligible_hour_usd', Number(e.target.value))}/></label>
          <label className="field">Credit cap (USD)<input type="number" min="1" value={contract.sla.cap_usd} onChange={e => editSla('cap_usd', Number(e.target.value))}/></label>
          <label className="field">Claim window (days)<input type="number" min="1" value={contract.sla.claim_window_days} onChange={e => editSla('claim_window_days', Number(e.target.value))}/></label>
        </div>
        <label className="field">Clause excerpt<textarea rows={4} value={contract.sla.source_quote || ''} onChange={e => editSla('source_quote', e.target.value)} placeholder="Paste the actual hourly-credit and planned-maintenance clause."/></label>
        <p className="muted">This pilot supports hourly credits with a planned-maintenance exclusion. Manually entered terms have no archived PDF and must be checked against the source.</p>
        <div className="flowActions"><button className="uiButton" disabled={busy || !!savedId} onClick={saveContract}>{busy ? 'Saving…' : savedId ? 'Contract saved' : 'Save contract and continue'}</button>{savedId && <button className="uiButton secondary" onClick={() => setStage(2)}>Continue to incident <span aria-hidden="true">→</span></button>}</div>
      </article>}
      {stage === 2 && <article className="uiCard intakeCard"><div className="flowSectionHead"><span className="sectionKicker">STEP 02 / 02</span><h2>Describe the incident</h2><p>Provide the timeline and observed signals. These entries are marked as operator supplied until a reviewer checks the source records.</p></div><div className="selectedContract"><div><span>CONTRACT IN USE</span><strong>{contract.customer} / {contract.vendor}</strong><small>{contract.sla.title} · {contract.id}</small></div><button className="uiButton text" onClick={() => setStage(1)}>Change contract</button></div>
        <p className="muted">Enter timestamps in your local time zone. These entries are treated as operator statements until a reviewer checks the source records.</p>
        <label className="field">Incident ID (optional)<input value={incident.id} onChange={e => setIncident({ ...incident, id: e.target.value })} placeholder="Leave blank to generate"/></label>
        <div className="fieldsTwo">
          <label className="field">Started<input type="datetime-local" value={incident.start} onChange={e => setIncident({ ...incident, start: e.target.value })}/></label>
          <label className="field">Ended<input type="datetime-local" value={incident.end} onChange={e => setIncident({ ...incident, end: e.target.value })}/></label>
          <label className="field">Ticket opened<input type="datetime-local" value={incident.ticket} onChange={e => setIncident({ ...incident, ticket: e.target.value })}/></label>
          <label className="field">Vendor acknowledged<input type="datetime-local" value={incident.ack} onChange={e => setIncident({ ...incident, ack: e.target.value })}/></label>
          <label className="field">Severity<select value={incident.severity} onChange={e => setIncident({ ...incident, severity: e.target.value })}><option value="critical">Critical</option><option value="major">Major</option><option value="minor">Minor</option></select></label>
          <label className="field">Pump state<input value={incident.pump} onChange={e => setIncident({ ...incident, pump: e.target.value })} placeholder="fault / degraded"/></label>
          <label className="field">Coolant pressure (bar, optional)<input type="number" step="0.1" value={incident.pressure} onChange={e => setIncident({ ...incident, pressure: e.target.value })}/></label>
        </div>
        <label className="field">Maintenance status<select value={maintenance.mode} onChange={e => setMaintenance({ ...maintenance, mode: e.target.value })}><option value="">Choose one</option><option value="none">No window reported</option><option value="recorded">Window recorded</option></select></label>
        {maintenance.mode === 'recorded' && <div className="fieldsTwo"><label className="field">Window start<input type="datetime-local" value={maintenance.start} onChange={e => setMaintenance({ ...maintenance, start: e.target.value })}/></label><label className="field">Window end<input type="datetime-local" value={maintenance.end} onChange={e => setMaintenance({ ...maintenance, end: e.target.value })}/></label><label className="field wide">Window description<input value={maintenance.description} onChange={e => setMaintenance({ ...maintenance, description: e.target.value })}/></label></div>}
        <label className="field">Operator notes<textarea rows={3} value={incident.note} onChange={e => setIncident({ ...incident, note: e.target.value })}/></label>
        <div className="flowActions"><button className="uiButton" disabled={busy || !savedId} onClick={createCase}>{busy ? 'Investigating…' : 'Create case for review'} <span aria-hidden="true">→</span></button></div>
        {created && <div className="successBox">Case {created.id} saved as {created.state.replaceAll('_', ' ')}. <a href={`/review?case=${encodeURIComponent(created.id)}`}>Open case review</a></div>}
      </article>}
    </section>
    <div className="flowAssurance"><strong>What happens next</strong><span>InfraClaim checks the clause and evidence, calculates a proposed credit, and places the case in the review queue. It does not contact the vendor.</span></div>
  </AppShell>
}

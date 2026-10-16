'use client'

import { useEffect, useState } from 'react'

type Window = { start: string; end: string; description: string }
type Incident = {
  id: string; service: string; vendor: string; start: string; end: string;
  severity: string; ticket_opened_at: string; vendor_acknowledged_at: string;
  telemetry: Record<string, string | number>; maintenance_windows: Window[]; notes: string[]
}
type CorrectionCase = { id: string; version: number; incident_snapshot?: Incident }
const local = (value: string) => {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? '' :
    new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
const iso = (value: string) => {
  const date = new Date(value)
  if (!value || Number.isNaN(date.valueOf())) throw new Error('Complete every required date and time.')
  return date.toISOString()
}
const emptyWindow = (): Window => ({ start: '', end: '', description: '' })

export default function CorrectionForm({ caseData, onSaved }: {
  caseData: CorrectionCase; onSaved: (result: any) => void
}) {
  const [times, setTimes] = useState({ start: '', end: '', ticket: '', ack: '' })
  const [severity, setSeverity] = useState('critical')
  const [pump, setPump] = useState('')
  const [pressure, setPressure] = useState('')
  const [windows, setWindows] = useState<Window[]>([])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const incident = caseData.incident_snapshot
    if (!incident) return
    setTimes({ start: local(incident.start), end: local(incident.end),
      ticket: local(incident.ticket_opened_at), ack: local(incident.vendor_acknowledged_at) })
    setSeverity(incident.severity)
    setPump(String(incident.telemetry.pump_state || ''))
    setPressure(incident.telemetry.coolant_pressure_bar == null ? '' : String(incident.telemetry.coolant_pressure_bar))
    setWindows(incident.maintenance_windows.map(item => ({
      start: local(item.start), end: local(item.end), description: item.description
    })))
    setNote(''); setError('')
  }, [caseData.id, caseData.version, caseData.incident_snapshot])

  function changeWindow(index: number, key: keyof Window, value: string) {
    setWindows(current => current.map((item, i) => i === index ? { ...item, [key]: value } : item))
  }
  function usePilotValues() {
    setTimes({ start: local('2026-10-05T14:03:00Z'), end: local('2026-10-05T18:03:00Z'),
      ticket: local('2026-10-05T14:05:00Z'), ack: local('2026-10-05T14:29:00Z') })
    setSeverity('critical'); setPump('fault'); setPressure('1.7')
    setWindows([{ start: local('2026-10-05T12:00:00Z'), end: local('2026-10-05T13:00:00Z'),
      description: 'Scheduled cooling-loop inspection completed before incident.' }])
    setNote('Aligned the entered incident with the bundled synthetic ticket, telemetry, and maintenance exports.')
  }
  async function save() {
    const original = caseData.incident_snapshot
    if (!original) return
    setBusy(true); setError('')
    try {
      if (!pump.trim()) throw new Error('Enter the observed pump state.')
      const telemetry: Record<string, string | number> = { ...original.telemetry, pump_state: pump.trim() }
      if (pressure.trim()) telemetry.coolant_pressure_bar = Number(pressure)
      else delete telemetry.coolant_pressure_bar
      const incident = {
        ...original, start: iso(times.start), end: iso(times.end),
        ticket_opened_at: iso(times.ticket), vendor_acknowledged_at: iso(times.ack),
        severity, telemetry,
        maintenance_windows: windows.map(item => ({
          start: iso(item.start), end: iso(item.end), description: item.description.trim()
        })),
        notes: [...original.notes, `Operator correction: ${note.trim()}`],
      }
      const response = await fetch(`/api/cases/${encodeURIComponent(caseData.id)}/amend`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: caseData.version, incident, note: note.trim() }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `Correction failed (${response.status})`)
      onSaved(result)
      setNote('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Correction could not be saved.') }
    finally { setBusy(false) }
  }
  return <details className="correctionPanel">
    <summary>Correct incident information</summary>
    <p>Use this when a reviewer requests a correction. Changes are recorded with the previous values and reassessed. All entries remain operator supplied; a reviewer must make a new decision.</p>
    {caseData.incident_snapshot?.id === 'pilot_manual_001' && <button className="uiButton secondary" type="button" onClick={usePilotValues}>Fill bundled pilot values</button>}
    <div className="fieldsTwo">
      <label className="field">Incident started<input type="datetime-local" value={times.start} onChange={e => setTimes({ ...times, start: e.target.value })}/></label>
      <label className="field">Incident ended<input type="datetime-local" value={times.end} onChange={e => setTimes({ ...times, end: e.target.value })}/></label>
      <label className="field">Ticket opened<input type="datetime-local" value={times.ticket} onChange={e => setTimes({ ...times, ticket: e.target.value })}/></label>
      <label className="field">Vendor acknowledged<input type="datetime-local" value={times.ack} onChange={e => setTimes({ ...times, ack: e.target.value })}/></label>
      <label className="field">Severity<select value={severity} onChange={e => setSeverity(e.target.value)}><option value="critical">Critical</option><option value="major">Major</option><option value="minor">Minor</option></select></label>
      <label className="field">Pump state<input value={pump} onChange={e => setPump(e.target.value)}/></label>
      <label className="field">Coolant pressure (bar)<input type="number" step="0.1" value={pressure} onChange={e => setPressure(e.target.value)}/></label>
    </div>
    <div className="correctionWindowHead"><strong>Maintenance windows</strong><button className="uiButton secondary" type="button" disabled={windows.length >= 25} onClick={() => setWindows(current => [...current, emptyWindow()])}>Add window</button></div>
    {windows.length === 0 && <p>No maintenance window recorded.</p>}
    {windows.map((window, index) => <div className="correctionWindow" key={index}><div className="fieldsTwo">
      <label className="field">Window start<input type="datetime-local" value={window.start} onChange={e => changeWindow(index, 'start', e.target.value)}/></label>
      <label className="field">Window end<input type="datetime-local" value={window.end} onChange={e => changeWindow(index, 'end', e.target.value)}/></label>
      <label className="field wide">Description<input value={window.description} onChange={e => changeWindow(index, 'description', e.target.value)}/></label>
    </div><button className="uiButton text dangerText" type="button" onClick={() => setWindows(current => current.filter((_, i) => i !== index))}>Remove window</button></div>)}
    <label className="field">What changed and why?<textarea rows={3} value={note} onChange={e => setNote(e.target.value)}/></label>
    {error && <div className="uiAlert error" role="alert">{error}</div>}
    <button className="uiButton" type="button" disabled={busy || note.trim().length < 5} onClick={save}>{busy ? 'Reassessing…' : 'Save correction and reassess'}</button>
  </details>
}

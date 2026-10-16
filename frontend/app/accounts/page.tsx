'use client'

import { FormEvent, useEffect, useState } from 'react'
import AppShell from '../AppShell'
import PasswordField from '../PasswordField'

type User = { username: string; display_name: string; role: string; disabled: boolean }
type Event = { at: string; actor: string; action: string; subject: string }
async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/api${path}`, init)
  const value = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(value.detail || `Request failed (${response.status})`)
  return value
}
const json = (body: object): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export default function Accounts() {
  const [allowed, setAllowed] = useState(false)
  const [users, setUsers] = useState<User[]>([])
  const [events, setEvents] = useState<Event[]>([])
  const [form, setForm] = useState({ username: '', display_name: '', role: 'operator', password: '' })
  const [resetFor, setResetFor] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function refresh() {
    const [nextUsers, nextEvents] = await Promise.all([request('/admin/users'), request('/admin/auth-events')])
    setUsers(nextUsers); setEvents(nextEvents)
  }
  useEffect(() => {
    request('/auth/me').then(identity => {
      if (identity.role !== 'admin') { setError('Administrator account required.'); return }
      setAllowed(true); refresh().catch(cause => setError(String(cause)))
    }).catch(() => {})
  }, [])
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      await request('/admin/users', json(form)); setForm({ username: '', display_name: '', role: 'operator', password: '' })
      await refresh(); setMessage('Account created. Give the password privately to its owner.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Account could not be created.') }
    finally { setBusy(false) }
  }
  async function changeState(user: User) {
    setBusy(true); setError(''); setMessage('')
    try {
      await request(`/admin/users/${encodeURIComponent(user.username)}/state`, json({ disabled: !user.disabled }))
      await refresh(); setMessage(`${user.username} ${user.disabled ? 'enabled' : 'disabled'}; active sessions were revoked if disabled.`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Account could not be updated.') }
    finally { setBusy(false) }
  }
  async function reset(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      await request(`/admin/users/${encodeURIComponent(resetFor)}/password`, json({ password: newPassword }))
      setNewPassword(''); setResetFor(''); await refresh()
      setMessage('Password changed and all existing sessions for that account were revoked.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Password could not be changed.') }
    finally { setBusy(false) }
  }
  return <AppShell active="accounts" eyebrow="ACCESS CONTROL" title="Accounts"
    description="Give each pilot participant a named account. Decisions and corrections use their signed-in identity.">
    {error && <div className="uiAlert error" role="alert">{error}</div>}
    {message && <div className="uiAlert success" role="status">{message}</div>}
    {allowed && <div className="accountGrid"><section className="uiCard accountCard"><span className="sectionKicker">01 / PEOPLE</span><h2>Pilot accounts</h2>
      {users.map(user => <div className="accountRow" key={user.username}><div><strong>{user.display_name}</strong><small>{user.username} · {user.role} · {user.disabled ? 'Disabled' : 'Active'}</small></div><div className="accountActions"><button className="uiButton text" disabled={busy} onClick={() => { setResetFor(user.username); setNewPassword('') }}>Reset password</button><button className="uiButton secondary" disabled={busy} onClick={() => changeState(user)}>{user.disabled ? 'Enable' : 'Disable'}</button></div></div>)}
      {resetFor && <form className="accountReset" onSubmit={reset}><h3>Reset password for {resetFor}</h3><PasswordField label="New password" autoComplete="new-password" minLength={14} value={newPassword} onChange={setNewPassword}/><p className="muted">At least 14 characters. Existing sessions will end.</p><div className="accountActions"><button className="uiButton" disabled={busy}>Save new password</button><button className="uiButton text" type="button" onClick={() => setResetFor('')}>Cancel</button></div></form>}
    </section><section className="uiCard accountCard"><span className="sectionKicker">02 / ADD ACCOUNT</span><h2>Create account</h2><form onSubmit={create} className="accountForm">
      <label className="field">Username<input required minLength={3} maxLength={64} value={form.username} onChange={event => setForm({ ...form, username: event.target.value })}/></label>
      <label className="field">Display name<input required minLength={2} maxLength={100} value={form.display_name} onChange={event => setForm({ ...form, display_name: event.target.value })}/></label>
      <label className="field">Role<select value={form.role} onChange={event => setForm({ ...form, role: event.target.value })}><option value="operator">Operator · enter and correct</option><option value="reviewer">Reviewer · decide</option><option value="admin">Admin · manage and simulate</option></select></label>
      <PasswordField label="Initial password" autoComplete="new-password" minLength={14} value={form.password} onChange={value => setForm({ ...form, password: value })}/><button className="uiButton" disabled={busy}>Create account</button>
    </form></section><section className="uiCard accountCard accountWide"><span className="sectionKicker">03 / SECURITY LOG</span><h2>Recent account changes</h2>{events.length ? events.map((event, index) => <p key={index} className="accountEvent"><time>{new Date(event.at).toLocaleString()}</time><strong>{event.actor}</strong> {event.action.replaceAll('_', ' ')} <strong>{event.subject}</strong></p>) : <p className="muted">No account changes recorded.</p>}</section></div>}
  </AppShell>
}

'use client'

import { FormEvent, useEffect, useState } from 'react'
import PasswordField from '../PasswordField'

export default function SignupPage() {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    fetch('/api/auth/signup-status').then(response => response.json())
      .then(result => setEnabled(Boolean(result.enabled))).catch(() => setEnabled(false))
  }, [])

  async function signup(event: FormEvent) {
    event.preventDefault()
    if (password !== confirmPassword) { setError('Passwords do not match.'); return }
    setBusy(true); setError('')
    try {
      const response = await fetch('/api/auth/signup', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName, username, password }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Account could not be created.')
      setPending(true); setPassword(''); setConfirmPassword('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Account could not be created.') }
    finally { setBusy(false) }
  }

  return <main className="loginPage"><form className="uiCard loginCard" onSubmit={signup}>
    <span className="sectionKicker">INFRACLAIM · INTERNAL PILOT</span><h1>Create your account</h1>
    <p>An administrator must approve your account before you can access the pilot workspace. Vendor actions remain simulated.</p>
    {pending ? <div className="successBox" role="status">Account requested. Ask the pilot administrator to enable your account, then sign in.</div> : enabled === false ? <div className="uiAlert error" role="alert">Sign-up is unavailable. Ask the pilot administrator for an account.</div> : <>
      <label className="field">Your name<input autoComplete="name" required minLength={2} maxLength={100} value={displayName} onChange={event => setDisplayName(event.target.value)}/></label>
      <label className="field">Username<input autoComplete="username" required minLength={3} maxLength={64} pattern="[A-Za-z0-9_-]+" title="Use letters, numbers, dashes or underscores" value={username} onChange={event => setUsername(event.target.value)}/></label>
      <PasswordField label="Password" autoComplete="new-password" minLength={14} maxLength={1024} value={password} onChange={setPassword}/>
      <PasswordField label="Confirm password" autoComplete="new-password" minLength={14} value={confirmPassword} onChange={setConfirmPassword}/>
      <p className="authHint">Use at least 14 characters. This local pilot uses synthetic data only.</p>
      {error && <div className="uiAlert error" role="alert">{error}</div>}
      <button className="uiButton" disabled={busy || enabled !== true}>{busy ? 'Creating account…' : 'Create account'}</button>
    </>}
    <p className="authSwitch">Already have an account? <a href="/login">Sign in</a></p>
  </form></main>
}

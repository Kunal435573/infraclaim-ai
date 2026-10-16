'use client'

import { FormEvent, useEffect, useState } from 'react'
import PasswordField from '../PasswordField'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [signupEnabled, setSignupEnabled] = useState(false)
  useEffect(() => {
    fetch('/api/auth/signup-status').then(response => response.json())
      .then(result => setSignupEnabled(Boolean(result.enabled))).catch(() => {})
  }, [])
  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const response = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }) })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Sign-in failed')
      window.location.href = '/'
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Sign-in failed') }
    finally { setBusy(false) }
  }
  return <main className="loginPage"><form className="uiCard loginCard" onSubmit={login}>
    <span className="sectionKicker">INFRACLAIM · INTERNAL PILOT</span><h1>Sign in</h1>
    <p>Use your assigned account to open cases and record decisions. Vendor actions remain simulated.</p>
    <label className="field">Username<input autoComplete="username" required value={username} onChange={event => setUsername(event.target.value)}/></label>
    <PasswordField label="Password" autoComplete="current-password" value={password} onChange={setPassword}/>
    {error && <div className="uiAlert error" role="alert">{error}</div>}
    <button className="uiButton" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    {signupEnabled && <p className="authSwitch">Don’t have an account yet? <a href="/signup">Sign up first</a></p>}
  </form></main>
}

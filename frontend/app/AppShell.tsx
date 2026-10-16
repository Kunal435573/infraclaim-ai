'use client'

import { ReactNode, useEffect, useState } from 'react'

type Section = 'overview' | 'intake' | 'review' | 'accounts'
const nav: { href: string; label: string; key: Section; icon: ReactNode }[] = [
  { href: '/', label: 'Overview', key: 'overview', icon: <path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"/> },
  { href: '/intake', label: 'Open a case', key: 'intake', icon: <><path d="M12 5v14M5 12h14"/><circle cx="12" cy="12" r="9"/></> },
  { href: '/review', label: 'Review queue', key: 'review', icon: <><path d="M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5"/></> },
  { href: '/accounts', label: 'Accounts', key: 'accounts', icon: <><circle cx="12" cy="8" r="3"/><path d="M5 21v-2a7 7 0 0 1 14 0v2M4 4h2M18 4h2"/></> },
]

export default function AppShell({ active, eyebrow, title, description, actions, children }: {
  active: Section; eyebrow: string; title: string; description: string; actions?: ReactNode; children: ReactNode
}) {
  const [identity, setIdentity] = useState<{ username: string; display_name: string; role: string } | null>(null)
  useEffect(() => {
    fetch('/api/auth/me').then(async response => {
      if (response.status === 401) { window.location.replace('/login'); return }
      if (response.ok) setIdentity(await response.json())
    }).catch(() => {})
  }, [])
  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' })
    window.location.replace('/login')
  }
  if (!identity) return <main className="loginPage"><p>Checking your account…</p></main>
  return <div className="appShell">
    <a className="skipLink" href="#main-content">Skip to main content</a>
    <aside className="appSidebar" aria-label="Main navigation">
      <a className="appLogo" href="/" aria-label="InfraClaim AI overview"><span className="appLogoMark">IC</span><span><strong>InfraClaim</strong><small>AI · PILOT</small></span></a>
      <div className="sidebarGroupLabel">WORKSPACE</div>
      <nav className="appNav" aria-label="Primary">{nav.filter(item => (item.key !== 'intake' || identity.role !== 'reviewer') && (item.key !== 'accounts' || identity.role === 'admin')).map(item => <a key={item.key} href={item.href} aria-current={active === item.key ? 'page' : undefined} className={active === item.key ? 'selected' : ''}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{item.icon}</svg>{item.label}</a>)}</nav>
      <div className="sidebarFoot"><span className="statusDot"/>{identity.display_name} · {identity.role}<p>Vendor actions and credits are simulated. No real claim is sent.</p><button className="uiButton text" onClick={logout}>Sign out</button></div>
    </aside>
    <div className="appMain">
      <div className="appTopbar"><span>COMMERCIAL OPERATIONS <span className="topbarSlash">/</span> {nav.find(item => item.key === active)?.label.toUpperCase()}</span><span className="topbarPill">COOLING SLA PILOT</span><button className="uiButton text mobileSignout" onClick={logout}>Sign out</button></div>
      <main className="appContent" id="main-content" tabIndex={-1}><div className="appPageHead"><div><div className="appEyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{actions && <div className="appPageActions">{actions}</div>}</div>{children}</main>
    </div>
  </div>
}

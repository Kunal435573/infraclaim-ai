'use client'

import { useId, useState } from 'react'

export default function PasswordField({ label, value, onChange, autoComplete, minLength, maxLength }: {
  label: string
  value: string
  onChange: (value: string) => void
  autoComplete: 'current-password' | 'new-password'
  minLength?: number
  maxLength?: number
}) {
  const id = useId()
  const [visible, setVisible] = useState(false)

  return <div className="field passwordField">
    <label htmlFor={id}>{label}</label>
    <div className="passwordControl">
      <input id={id} type={visible ? 'text' : 'password'} autoComplete={autoComplete}
        required minLength={minLength} maxLength={maxLength} value={value}
        onChange={event => onChange(event.target.value)}/>
      <button type="button" className="passwordToggle" aria-label={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
        aria-pressed={visible} onClick={() => setVisible(!visible)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/>
          <circle cx="12" cy="12" r="3"/>
          {!visible && <path d="M3 3l18 18"/>}
        </svg>
      </button>
    </div>
  </div>
}

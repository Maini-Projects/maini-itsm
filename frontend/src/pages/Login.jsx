import { useState } from 'react'
import { useAuth } from '../auth'
import { api } from '../api'

export default function Login() {
  const { signIn } = useAuth()
  const [mode, setMode] = useState('signin') // signin | signup
  const [form, setForm] = useState({ full_name: '', email: '', password: '', confirm: '' })
  const [sent, setSent] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const signup = mode === 'signup'

  const switchMode = () => { setMode(signup ? 'signin' : 'signup'); setError(null); setSent(false) }

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    const email = form.email.trim()
    if (signup) {
      if (form.password.length < 8) return setError('Choose a password of at least 8 characters.')
      if (form.password !== form.confirm) return setError('The two passwords do not match.')
    }
    setBusy(true)
    try {
      if (signup) {
        await api.post('/auth/register', { email, full_name: form.full_name.trim(), password: form.password })
        setSent(true); setBusy(false)
      } else await signIn(email, form.password)
    } catch (err) { setError(err.message); setBusy(false) }
  }

  if (sent) {
    return (
      <div className="login-wrap">
        <div className="login-card">
          <div className="brand"><img src="/logo.png" alt="" /><span className="brand-text">MAINI CONSULTING</span></div>
          <h2>Request sent</h2>
          <p>Thanks, {form.full_name.trim()}. Your account is waiting for Administrator approval. You can sign in with {form.email.trim()} once it has been approved.</p>
          <button className="btn" type="button" onClick={switchMode}>Back to sign in</button>
        </div>
      </div>
    )
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="brand"><img src="/logo.png" alt="" /><span className="brand-text">MAINI CONSULTING</span></div>
        <h2>{signup ? 'Request an account' : 'Sign in'}</h2>
        <p>{signup ? 'An Administrator reviews every new account before you can sign in.' : 'Maini ITSM — incidents, problems, changes and releases.'}</p>
        {error && <div className="errorbox" role="alert">{error}</div>}
        {signup && (
          <div className="field">
            <label htmlFor="full_name">Full name</label>
            <input id="full_name" value={form.full_name} onChange={set('full_name')} autoComplete="name" maxLength={120} required autoFocus />
          </div>
        )}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={form.email} onChange={set('email')} autoComplete="username" required autoFocus={!signup} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={form.password} onChange={set('password')} autoComplete={signup ? 'new-password' : 'current-password'} minLength={signup ? 8 : undefined} maxLength={72} required />
        </div>
        {signup && (
          <div className="field">
            <label htmlFor="confirm">Confirm password</label>
            <input id="confirm" type="password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" maxLength={72} required />
          </div>
        )}
        <button className="btn" type="submit" disabled={busy}>
          {busy ? (signup ? 'Sending request…' : 'Signing in…') : (signup ? 'Request account' : 'Sign in')}
        </button>
        <p style={{ marginTop: 14, textAlign: 'center', fontSize: 13 }}>
          {signup ? 'Already have an account? ' : 'New here? '}
          <button type="button" className="link" onClick={switchMode} style={{ background: 'none', border: 0, padding: 0, color: 'var(--brand, #b0301c)', cursor: 'pointer', font: 'inherit', textDecoration: 'underline' }}>
            {signup ? 'Sign in' : 'Create an account'}
          </button>
        </p>
      </form>
    </div>
  )
}

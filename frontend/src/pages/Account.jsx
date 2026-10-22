import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import ChangePassword from '../components/ChangePassword'
import { ErrorBox, Field, Text, roleLabel, useToast } from '../components/ui'

const KEEP = [[1, '1 day'], [3, '3 days'], [7, '7 days'], [10, '10 days'], [30, '30 days'], [60, '60 days'], [90, '90 days'], [180, '6 months'], [365, '1 year']]

function AuditRetention() {
  const toast = useToast()
  const [keep, setKeep] = useState(10)
  const [error, setError] = useState(null)
  useEffect(() => { api.get('/audit/settings').then((s) => setKeep(s.retention_days)).catch(setError) }, [])
  const save = async (days) => {
    setError(null)
    try { await api.put('/audit/settings', { days }); setKeep(days); toast('Audit log period saved.') } catch (e) { setError(e) }
  }
  return (
    <div className="card" style={{ padding: 18, marginBottom: 16 }}>
      <h3 style={{ marginTop: 0 }}>Audit history</h3>
      <ErrorBox error={error} />
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label="Keep audit logs for">
          <select value={keep} onChange={(e) => save(Number(e.target.value))}>
            {KEEP.map(([d, l]) => <option key={d} value={d}>{l}{d === 10 ? ' (default)' : ''}</option>)}
          </select>
        </Field>
      </div>
    </div>
  )
}

export default function Account() {
  const { me, signOut } = useAuth()
  const [pw, setPw] = useState(false)
  return (
    <>
      <div className="eyebrow">Account</div>
      <h2 className="title">Account settings</h2>
      <div className="card" style={{ padding: 18, marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Profile</h3>
        <div className="form">
          <Field label="Name"><Text value={me.full_name} /></Field>
          <Field label="Email"><Text value={me.email} /></Field>
          <Field label="Role"><Text value={roleLabel(me.role)} /></Field>
          <Field label="Team"><Text value={me.team_name} /></Field>
          <Field label="Organization"><Text value={me.organization_name} /></Field>
        </div>
      </div>
      <div className="card" style={{ padding: 18, marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Security</h3>
        <button className="btn" onClick={() => setPw(true)}>Change password</button>{' '}
        <button className="btn2" onClick={signOut}>Sign out</button>
      </div>
      {me.role === 'admin' && <AuditRetention />}
      {pw && <ChangePassword onClose={() => setPw(false)} />}
    </>
  )
}

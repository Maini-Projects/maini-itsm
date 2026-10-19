import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, Empty, ErrorBox, Field, FormModal, Loading, roleLabel, useFetch, useToast } from '../components/ui'

const ROLES = ['admin', 'manager', 'employee']

export default function Admin() {
  const { me } = useAuth()
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [modal, setModal] = useState(null) // { kind: 'new' | 'edit' | 'password', user? }
  const teams = useFetch(() => api.get('/teams'))
  const { data, error, loading, reload } = useFetch(() => api.get('/users', { q: q.trim(), role }), [q, role])
  return (
    <>
      <div className="eyebrow">Administration</div>
      <h2 className="title">Users & Teams</h2>
      <p className="sub">Create accounts, set roles and teams, disable access and reset passwords. Each team has at most one Support Engineer.</p>
      <div className="toolbar">
        <div className="filters">
          <input placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search users" />
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role"><option value="">All roles</option>{ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}</select>
        </div>
        <button className="btn" onClick={() => setModal({ kind: 'new' })}>+ New User</button>
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Team</th><th>Status</th><th /></tr></thead>
          <tbody>
            {data?.map((u) => (
              <tr key={u.id}>
                <td><b>{u.full_name}</b>{u.id === me.id && <> <Badge tone="blue">You</Badge></>}</td><td>{u.email}</td><td>{roleLabel(u.role)}</td><td>{u.team_name || '—'}</td>
                <td><Badge tone={u.status === 'active' ? 'green' : u.status === 'pending' ? 'amber' : 'gray'}>{u.status}</Badge></td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="btn2" onClick={() => setModal({ kind: 'edit', user: u })}>Edit</button>{' '}
                  <button className="btn2" onClick={() => setModal({ kind: 'password', user: u })}>Reset password</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.length && <Empty>No users match.</Empty>}
      </div>
      {modal?.kind === 'new' && <UserModal teams={teams.data || []} onClose={() => setModal(null)} onSaved={reload} />}
      {modal?.kind === 'edit' && <UserModal user={modal.user} self={modal.user.id === me.id} teams={teams.data || []} onClose={() => setModal(null)} onSaved={reload} />}
      {modal?.kind === 'password' && <PasswordModal user={modal.user} onClose={() => setModal(null)} />}
    </>
  )
}

function UserModal({ user, self, teams, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ full_name: user?.full_name || '', email: user?.email || '', password: '', role: user?.role || 'employee', team_id: user?.team_id || '', status: user?.status || 'active' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const needsTeam = f.role !== 'admin'
  const submit = async () => {
    if (needsTeam && !f.team_id) throw new Error('Choose a team for Support Engineers and Customers.')
    const team_id = needsTeam ? f.team_id : null
    if (user) await api.patch(`/users/${user.id}`, { full_name: f.full_name, role: f.role, team_id, status: f.status })
    else await api.post('/users', { email: f.email.trim(), full_name: f.full_name, password: f.password, role: f.role, team_id })
    toast(user ? 'User updated.' : 'User created.')
    onSaved()
  }
  return (
    <FormModal title={user ? `Edit ${user.full_name}` : 'New user'} onClose={onClose} onSubmit={submit} width={560}>
      <div className="form">
        <Field label="Full name"><input value={f.full_name} onChange={set('full_name')} required autoFocus /></Field>
        <Field label="Email">{user ? <div className="ro">{user.email}</div> : <input type="email" value={f.email} onChange={set('email')} required />}</Field>
        {!user && <Field label="Temporary password" hint="At least 8 characters. They can change it after signing in."><input type="text" value={f.password} onChange={set('password')} minLength={8} required autoComplete="off" /></Field>}
        <Field label="Role">
          <select value={f.role} onChange={set('role')} disabled={self}>{ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}</select>
        </Field>
        <Field label="Team" hint={needsTeam ? 'Required. A Support Engineer sees only their own team.' : 'Administrators are not tied to a team.'}>
          <select value={needsTeam ? f.team_id : ''} onChange={set('team_id')} disabled={!needsTeam}><option value="">{needsTeam ? 'Choose a team' : '—'}</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
        </Field>
        {user && <Field label="Status"><select value={f.status} onChange={set('status')} disabled={self}><option value="active">active</option><option value="disabled">disabled</option></select></Field>}
        {self && <div className="hint" style={{ gridColumn: '1/-1', fontSize: 11.5, color: 'var(--muted)' }}>You cannot remove your own Administrator access or disable yourself.</div>}
      </div>
    </FormModal>
  )
}

function PasswordModal({ user, onClose }) {
  const toast = useToast()
  const [pw, setPw] = useState('')
  return (
    <FormModal title={`Reset password for ${user.full_name}`} submitLabel="Set password" onClose={onClose} width={480}
      onSubmit={async () => { await api.post(`/users/${user.id}/password`, { new_password: pw }); toast('Password updated.') }}>
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label="New password" hint="At least 8 characters. Tell the user directly; they can change it after signing in."><input type="text" value={pw} onChange={(e) => setPw(e.target.value)} minLength={8} required autoComplete="off" autoFocus /></Field>
      </div>
    </FormModal>
  )
}

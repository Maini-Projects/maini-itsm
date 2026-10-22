import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, Empty, ErrorBox, Field, FormModal, Loading, fmtShort, roleLabel, useFetch, useToast } from './ui'

const ROLES = ['admin', 'manager', 'employee']

// New-user sign-up requests, shown to Administrators in the Approval Queue.
export default function SignupRequests({ status }) {
  const { refreshCounts } = useAuth()
  const [modal, setModal] = useState(null) // { kind: 'approve' | 'reject', request }
  const teams = useFetch(() => api.get('/teams'))
  const { data, error, loading, reload } = useFetch(() => api.get('/signup-requests', { status }), [status])
  const changed = () => { reload(); refreshCounts() }
  if (status !== 'all' && data && !data.length && !error) return null
  return (
    <>
      <h3 style={{ margin: '22px 0 8px' }}>New user sign-ups</h3>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Requested</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            {data?.map((r) => (
              <tr key={r.id}>
                <td><b>{r.full_name}</b></td><td>{r.email}</td><td>{fmtShort(r.created_at)}</td>
                <td>
                  <Badge tone={{ pending: 'amber', approved: 'green', rejected: 'red' }[r.status]}>{r.status}</Badge>
                  {r.decided_by_name && <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 3 }}>{r.decided_by_name}</div>}
                </td>
                <td>
                  {r.status === 'pending' ? (
                    <span style={{ display: 'flex', gap: 6 }}>
                      <button className="btn" onClick={() => setModal({ kind: 'approve', request: r })}>Approve</button>
                      <button className="danger" onClick={() => setModal({ kind: 'reject', request: r })}>Reject</button>
                    </span>
                  ) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.length && <Empty>No sign-up requests to show.</Empty>}
      </div>
      {modal?.kind === 'approve' && <ApproveModal request={modal.request} teams={teams.data || []} onClose={() => setModal(null)} onSaved={changed} />}
      {modal?.kind === 'reject' && <RejectModal request={modal.request} onClose={() => setModal(null)} onSaved={changed} />}
    </>
  )
}

function ApproveModal({ request, teams, onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ role: 'employee', team_id: '' })
  const needsTeam = f.role !== 'admin'
  return (
    <FormModal title={`Approve ${request.full_name}`} submitLabel="Approve" onClose={onClose} width={480}
      onSubmit={async () => {
        if (needsTeam && !f.team_id) throw new Error('Choose a team for Support Engineers and Customers.')
        await api.post(`/signup-requests/${request.id}/approve`, { role: f.role, team_id: f.team_id || null })
        toast(`${request.full_name} can now sign in.`)
        onSaved()
      }}>
      <div className="form">
        <Field label="Email"><div className="ro">{request.email}</div></Field>
        <Field label="Role"><select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}</select></Field>
        <Field label="Team">
          <select value={f.team_id} onChange={(e) => setF({ ...f, team_id: e.target.value })}><option value="">{needsTeam ? 'Choose a team' : 'No team'}</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
        </Field>
      </div>
    </FormModal>
  )
}

function RejectModal({ request, onClose, onSaved }) {
  const toast = useToast()
  return (
    <FormModal title={`Reject ${request.full_name}?`} submitLabel="Reject request" danger onClose={onClose} width={480}
      onSubmit={async () => { await api.post(`/signup-requests/${request.id}/reject`); toast('Request rejected.'); onSaved() }}>
      <p style={{ fontSize: 13 }}>The login for {request.email} will be removed. They can sign up again later if this was a mistake.</p>
    </FormModal>
  )
}

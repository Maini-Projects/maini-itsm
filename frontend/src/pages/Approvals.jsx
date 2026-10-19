import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { DecisionModal } from '../components/ApprovalBox'
import { Badge, Empty, ErrorBox, Loading, Priority, RiskBadge, fmtShort, roleLabel, useFetch, useToast } from '../components/ui'

const TYPE_LABEL = { incident: 'Incident closure', change: 'Change', release: 'Release' }
const PATH = { incident: 'incidents', change: 'changes', release: 'releases' }

export default function Approvals() {
  const { me, refreshCounts } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const [deciding, setDeciding] = useState(null)
  const { data, error, loading, reload } = useFetch(() => api.get('/approvals', { status }), [status])

  const done = (msg) => { toast(msg); reload(); refreshCounts() }

  return (
    <>
      <div className="eyebrow">Governance</div>
      <h2 className="title">Approval Queue</h2>
      <p className="sub">
        {me.role === 'admin' ? 'Changes and releases waiting for your decision.' : 'The status of the changes and releases you raised. An Administrator decides them.'}
      </p>
      <div className="toolbar">
        <div className="filters">
          {['pending', 'approved', 'rejected', 'all'].map((s) => (
            <button key={s} className={status === s ? 'btn' : 'btn2'} onClick={() => setStatus(s)}>{s[0].toUpperCase() + s.slice(1)}</button>
          ))}
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Request</th><th>Type</th><th>Title</th><th>Priority / Risk</th><th>Requester</th><th>Approver</th><th>Requested</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            {data?.map((a) => (
              <tr key={a.id}>
                <td><Link className="link" to={`/${PATH[a.record_type]}/${a.record_id}`}>{a.record_number}</Link></td>
                <td>{a.change_type ? `${a.change_type} change` : TYPE_LABEL[a.record_type]}</td>
                <td><b>{a.title}</b></td>
                <td>{a.priority ? <Priority p={a.priority} /> : a.risk ? <RiskBadge risk={a.risk} /> : a.environment || '—'}</td>
                <td>{a.requested_by_name}</td>
                <td>{a.approver_role === 'admin' ? roleLabel('admin') : `${a.team_name || ''} ${roleLabel('manager')}`.trim()}</td>
                <td>{fmtShort(a.created_at)}</td>
                <td>
                  <Badge tone={{ pending: 'amber', approved: 'green', rejected: 'red' }[a.status]}>{a.status}</Badge>
                  {a.decided_by_name && <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 3 }}>{a.decided_by_name}{a.comment ? ` — “${a.comment}”` : ''}</div>}
                </td>
                <td>
                  {a.can_decide ? (
                    <span style={{ display: 'flex', gap: 6 }}>
                      <button className="btn" onClick={() => setDeciding({ id: a.id, decision: 'approved' })}>Approve</button>
                      <button className="danger" onClick={() => setDeciding({ id: a.id, decision: 'rejected' })}>Reject</button>
                    </span>
                  ) : a.status === 'pending' ? <span style={{ fontSize: 11, color: 'var(--muted)' }}>Awaiting {a.approver_role === 'admin' ? 'Administrator' : `team ${roleLabel('manager')}`}</span> : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.length && <Empty>{status === 'pending' ? 'Nothing is waiting for approval.' : 'No approvals to show.'}</Empty>}
      </div>
      {deciding && <DecisionModal approvalId={deciding.id} decision={deciding.decision} onClose={() => setDeciding(null)} onDone={done} />}
    </>
  )
}

import { useState } from 'react'
import { api } from '../api'
import { Badge, Field, FormModal, fmtDate, useAction } from './ui'

// Reject needs a reason, so it gets its own small form.
export function DecisionModal({ approvalId, decision, onClose, onDone }) {
  const [comment, setComment] = useState('')
  const reject = decision === 'rejected'
  return (
    <FormModal
      title={reject ? 'Reject request' : 'Approve request'} submitLabel={reject ? 'Reject' : 'Approve'} danger={reject}
      onClose={onClose} width={520}
      onSubmit={async () => { await api.post(`/approvals/${approvalId}/decision`, { decision, comment: comment.trim() || null }); onDone(reject ? 'Rejected and sent back.' : 'Approved.') }}
    >
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label={reject ? 'Reason (required)' : 'Comment (optional)'}>
          <textarea value={comment} onChange={(e) => setComment(e.target.value)} required={reject} autoFocus />
        </Field>
      </div>
    </FormModal>
  )
}

// Approval history of a change or release; an admin can decide a pending one right here.
export default function ApprovalBox({ approvals, canDecide, onChanged }) {
  const [deciding, setDeciding] = useState(null)
  const [, busy] = useAction()
  if (!approvals?.length) return null
  const pending = approvals.find((a) => a.status === 'pending')
  return (
    <div className="side">
      <h4>Approval</h4>
      {approvals.map((a) => (
        <div className="sr" key={a.id}>
          <label>{fmtDate(a.created_at)}</label>
          <b><Badge tone={{ pending: 'amber', approved: 'green', rejected: 'red' }[a.status]}>{a.status}</Badge></b>
          {a.decided_by_name && <div style={{ fontSize: 11.5, marginTop: 4 }}>by {a.decided_by_name}</div>}
          {a.comment && <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 3 }}>“{a.comment}”</div>}
        </div>
      ))}
      {pending && canDecide && (
        <div className="sideactions">
          <button className="btn" disabled={busy} onClick={() => setDeciding({ id: pending.id, decision: 'approved' })}>Approve</button>
          <button className="danger" disabled={busy} onClick={() => setDeciding({ id: pending.id, decision: 'rejected' })}>Reject…</button>
        </div>
      )}
      {pending && !canDecide && <div className="sideactions"><div className="note">Waiting for an admin to decide.</div></div>}
      {deciding && <DecisionModal approvalId={deciding.id} decision={deciding.decision} onClose={() => setDeciding(null)} onDone={() => onChanged()} />}
    </div>
  )
}

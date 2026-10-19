import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import ApprovalBox from '../components/ApprovalBox'
import {
  Badge, Empty, ErrorBox, Field, FormModal, Loading, Pager, RiskBadge, StatusBadge, Text, Timeline, Workflow, fmtDate,
  fmtShort, fromInputDate, toInputDate, useAction, useDebounced, useFetch,
} from '../components/ui'

const STATUSES = ['Draft', 'Submitted', 'Under Review', 'Approval Pending', 'Scheduled', 'Implementation', 'Implemented', 'Closed']
const LEVELS = ['High', 'Medium', 'Low']
const TYPES = ['Standard', 'Normal', 'Emergency']
const LIMIT = 25

export function ChangeList() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [status, setStatus] = useState('')
  const [risk, setRisk] = useState('')
  const [offset, setOffset] = useState(0)
  const [creating, setCreating] = useState(false)
  const dq = useDebounced(q)
  useEffect(() => setOffset(0), [dq, type, status, risk])
  const { data, error, loading } = useFetch(() => api.get('/changes', { q: dq.trim(), type, status, risk, limit: LIMIT, offset }), [dq, type, status, risk, offset])
  return (
    <>
      <div className="eyebrow">Change Management</div>
      <h2 className="title">Change Requests</h2>
      <p className="sub">Standard, normal and emergency changes with risk, approval and scheduling. Managers raise changes; an admin approves them.</p>
      <div className="toolbar">
        <div className="filters">
          <input placeholder="Search changes" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search changes" />
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Type"><option value="">All types</option>{TYPES.map((t) => <option key={t}>{t}</option>)}</select>
          <select value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Risk"><option value="">All risks</option>{LEVELS.map((t) => <option key={t}>{t}</option>)}</select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
        </div>
        <button className="btn" onClick={() => setCreating(true)}>+ New Change</button>
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Change</th><th>Title</th><th>Type</th><th>Service</th><th>Requester</th><th>Risk</th><th>Status</th><th>Planned Start</th></tr></thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id}>
                <td><Link className="link" to={`/changes/${c.id}`}>{c.number}</Link></td><td><b>{c.title}</b></td>
                <td>{c.type === 'Emergency' ? <Badge tone="red">Emergency</Badge> : c.type}</td><td>{c.service_name || '—'}</td>
                <td>{c.requester_name}</td><td><RiskBadge risk={c.risk} /></td><td><StatusBadge status={c.status} /></td><td>{fmtShort(c.planned_start)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.items.length && <Empty>No changes match.</Empty>}
        {data && <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </div>
      {creating && <NewChange onClose={() => setCreating(false)} onCreated={(c) => navigate(`/changes/${c.id}`)} />}
    </>
  )
}

function NewChange({ onClose, onCreated }) {
  const services = useFetch(() => api.get('/services'))
  const [f, setF] = useState({ title: '', type: 'Normal', risk: 'Medium', service_id: '', implementation_plan: '', test_plan: '', backout_plan: '', planned_start: '', planned_end: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async () => {
    const body = { title: f.title, type: f.type, risk: f.risk, planned_start: fromInputDate(f.planned_start), planned_end: fromInputDate(f.planned_end), service_id: f.service_id || null }
    ;['implementation_plan', 'test_plan', 'backout_plan'].forEach((k) => { if (f[k]) body[k] = f[k] })
    onCreated(await api.post('/changes', body))
  }
  return (
    <FormModal title="New Change Request" submitLabel="Create draft" onClose={onClose} onSubmit={submit}>
      <div className="form">
        <Field label="Title" wide><input value={f.title} onChange={set('title')} minLength={3} maxLength={200} required autoFocus /></Field>
        <Field label="Type"><select value={f.type} onChange={set('type')}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="Risk"><select value={f.risk} onChange={set('risk')}>{LEVELS.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="Service"><select value={f.service_id} onChange={set('service_id')}><option value="">None</option>{(services.data || []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
        <div />
        <Field label="Planned start"><input type="datetime-local" value={f.planned_start} onChange={set('planned_start')} /></Field>
        <Field label="Planned end"><input type="datetime-local" value={f.planned_end} onChange={set('planned_end')} /></Field>
        <Field label="Implementation plan" wide hint="Required before it can go for approval."><textarea value={f.implementation_plan} onChange={set('implementation_plan')} /></Field>
        <Field label="Backout plan" wide hint="Required before it can go for approval."><textarea value={f.backout_plan} onChange={set('backout_plan')} /></Field>
        <Field label="Test plan" wide><textarea value={f.test_plan} onChange={set('test_plan')} /></Field>
      </div>
    </FormModal>
  )
}

function nextActions(c) {
  const map = {
    Draft: { label: 'Submit', to: 'Submitted' },
    Submitted: { label: 'Start review', to: 'Under Review' },
    'Under Review': { label: 'Send for approval', to: 'Approval Pending' },
    Scheduled: { label: 'Start implementation', to: 'Implementation' },
    Implementation: { label: 'Mark implemented', to: 'Implemented' },
    Implemented: { label: 'Close change', to: 'Closed' },
  }
  return c.can_manage && map[c.status] ? [{ ...map[c.status], primary: true }] : []
}

export function ChangeDetail() {
  const { id } = useParams()
  const { me, refreshCounts } = useAuth()
  const navigate = useNavigate()
  const chg = useFetch(() => api.get(`/changes/${id}`), [id])
  const activity = useFetch(() => api.get(`/changes/${id}/activity`), [id])
  const [tab, setTab] = useState('details')
  const [run, busy] = useAction()

  if (chg.loading && !chg.data) return <Loading />
  if (chg.error) return <><button className="back" onClick={() => navigate('/changes')}>‹ Back to changes</button><ErrorBox error={chg.error} /></>
  const c = chg.data
  const refresh = () => { chg.reload(); activity.reload(); refreshCounts() }
  const move = (to) => run(async () => { await api.post(`/changes/${id}/transition`, { to_status: to }); refresh() }, `Moved to ${to}.`)

  return (
    <>
      <button className="back" onClick={() => navigate('/changes')}>‹ Back to changes</button>
      <div className="dtitle">
        <h2>{c.number}</h2><StatusBadge status={c.status} /><RiskBadge risk={c.risk} />
        {c.type === 'Emergency' && <Badge tone="red">Emergency</Badge>}
      </div>
      <p className="sub">{c.title}</p>
      <Workflow steps={STATUSES} current={c.status} />
      <div className="detail">
        <div className="card">
          <div className="tabs">
            {[['details', 'Details'], ['activity', 'Activity']].map(([k, label]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>)}
          </div>
          {tab === 'details' && <ChangeForm c={c} me={me} onSaved={refresh} />}
          {tab === 'activity' && <div className="incident-activity"><Timeline events={activity.data} /></div>}
        </div>
        <div>
          <div className="side">
            <h4>Summary</h4>
            {[['Type', c.type], ['Risk', c.risk], ['Service', c.service_name || '—'], ['Team', c.team_name || '—'], ['Requester', c.requester_name],
              ['Planned start', fmtDate(c.planned_start)], ['Planned end', fmtDate(c.planned_end)], ['Created', fmtDate(c.created_at)]].map(([k, v]) => <div className="sr" key={k}><label>{k}</label><b>{v}</b></div>)}
            {c.releases.length > 0 && <div className="sr"><label>In releases</label><b>{c.releases.map((r) => <div key={r.id}><Link className="link" to={`/releases/${r.id}`}>{r.number}</Link> {r.name}</div>)}</b></div>}
          </div>
          {nextActions(c).length > 0 && (
            <div className="side"><h4>Actions</h4>
              <div className="sideactions">
                {nextActions(c).map((a) => <button key={a.label} className="btn" disabled={busy} onClick={() => move(a.to)}>{a.label}</button>)}
                {c.status === 'Under Review' && <div className="note">Needs an implementation plan, backout plan and planned start before approval.</div>}
              </div>
            </div>
          )}
          <ApprovalBox approvals={c.approvals} canDecide={me.role === 'admin'} onChanged={refresh} />
        </div>
      </div>
    </>
  )
}

function ChangeForm({ c, me, onSaved }) {
  const services = useFetch(() => api.get('/services'))
  const canEdit = c.can_manage && c.status !== 'Closed' && (c.status === 'Draft' || me.role === 'admin')
  const initial = () => ({ title: c.title, type: c.type, risk: c.risk, service_id: c.service_id || '', implementation_plan: c.implementation_plan || '', test_plan: c.test_plan || '', backout_plan: c.backout_plan || '', planned_start: toInputDate(c.planned_start), planned_end: toInputDate(c.planned_end) })
  const [f, setF] = useState(initial)
  const [run, busy] = useAction()
  useEffect(() => setF(initial()), [c.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = (e) => {
    e.preventDefault()
    const init = initial(), changes = {}
    Object.keys(f).forEach((k) => {
      if (f[k] === init[k]) return
      changes[k] = k === 'service_id' ? f[k] || null : k.startsWith('planned') ? fromInputDate(f[k]) : f[k]
    })
    if (!Object.keys(changes).length) return
    run(async () => { await api.patch(`/changes/${c.id}`, changes); onSaved() }, 'Change updated.')
  }
  return (
    <form className="form" onSubmit={save}>
      <Field label="Title" wide>{canEdit ? <input value={f.title} onChange={set('title')} minLength={3} required /> : <Text value={c.title} />}</Field>
      <Field label="Type">{canEdit ? <select value={f.type} onChange={set('type')}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select> : <Text value={c.type} />}</Field>
      <Field label="Risk">{canEdit ? <select value={f.risk} onChange={set('risk')}>{LEVELS.map((t) => <option key={t}>{t}</option>)}</select> : <Text value={c.risk} />}</Field>
      <Field label="Service">{canEdit ? <select value={f.service_id} onChange={set('service_id')}><option value="">None</option>{(services.data || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select> : <Text value={c.service_name} />}</Field>
      <div />
      <Field label="Planned start">{canEdit ? <input type="datetime-local" value={f.planned_start} onChange={set('planned_start')} /> : <Text value={c.planned_start && fmtDate(c.planned_start)} />}</Field>
      <Field label="Planned end">{canEdit ? <input type="datetime-local" value={f.planned_end} onChange={set('planned_end')} /> : <Text value={c.planned_end && fmtDate(c.planned_end)} />}</Field>
      <Field label="Implementation plan" wide>{canEdit ? <textarea value={f.implementation_plan} onChange={set('implementation_plan')} /> : <Text value={c.implementation_plan} />}</Field>
      <Field label="Backout plan" wide>{canEdit ? <textarea value={f.backout_plan} onChange={set('backout_plan')} /> : <Text value={c.backout_plan} />}</Field>
      <Field label="Test plan" wide>{canEdit ? <textarea value={f.test_plan} onChange={set('test_plan')} /> : <Text value={c.test_plan} />}</Field>
      {canEdit && <div className="formactions"><button className="btn" disabled={busy}>Save changes</button></div>}
      {!canEdit && c.status !== 'Closed' && <div className="hint" style={{ gridColumn: '1/-1', fontSize: 11.5, color: 'var(--muted)' }}>A change can be edited while it is a Draft (admins can edit until it is closed).</div>}
    </form>
  )
}

import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ProjectFilter, useCustomers } from '../components/Customer'
import NoteBox from '../components/NoteBox'
import ApprovalBox from '../components/ApprovalBox'
import { urlParam,
  DetailTitle, FieldBar, statusField, Badge, Empty, ErrorBox, Field, FormModal, Loading, Pager, RiskBadge, StatusBadge, Text, Timeline, Workflow, fmtDate,
  fmtShort, fromInputDate, toInputDate, useAction, useDebounced, useFetch,
  useTab,
} from '../components/ui'
import CountPill from '../components/CountPill'

const STATUSES = ['Draft', 'Submitted', 'Under Review', 'Approval Pending', 'Scheduled', 'Implementation', 'Implemented', 'Closed']
const LEVELS = ['High', 'Medium', 'Low']
const TYPES = ['Standard', 'Normal', 'Emergency']
const LIMIT = 25

export function ChangeList() {
  const { me } = useAuth()
  const cust = useCustomers()
  const [projectId, setProjectId] = useState('')
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [type, setType] = useState(urlParam('type'))
  const [status, setStatus] = useState(urlParam('status'))
  const [risk, setRisk] = useState(urlParam('risk'))
  const [offset, setOffset] = useState(0)
  const [sp, setSp] = useSearchParams()
  const [creating, setCreating] = useState(sp.get('new') === '1' && me.role !== 'employee')
  useEffect(() => { if (sp.get('new')) { sp.delete('new'); setSp(sp, { replace: true }) } }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const dq = useDebounced(q)
  useEffect(() => setOffset(0), [dq, type, status, risk, projectId])
  const { data, error, loading } = useFetch(() => api.get('/changes', { q: dq.trim(), type, status, risk, project_id: projectId || undefined, limit: LIMIT, offset }), [dq, type, status, risk, projectId, offset])
  return (
    <>
      <div className="eyebrow">Change Management <CountPill of="changes" /></div>
      <h2 className="title">Change Requests</h2>
      <div className="toolbar">
        <div className="filters">
          <ProjectFilter cust={cust} value={projectId} onChange={setProjectId} />
          <input placeholder="Search changes" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search changes" />
          <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Type"><option value="">Type</option>{TYPES.map((t) => <option key={t}>{t}</option>)}</select>
          <select value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Risk"><option value="">Risk</option>{LEVELS.map((t) => <option key={t}>{t}</option>)}</select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Status</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
        </div>
        {me.role !== 'employee' ? <button className="btn" onClick={() => setCreating(true)}>+ New Change</button> : <span />}
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Change</th>{cust.multi && <th>Project</th>}<th>Title</th><th>Type</th><th>Application</th><th>Requester</th><th>Risk</th><th>Status</th><th>Planned Start</th></tr></thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id}>
                <td><Link className="link" to={`/changes/${c.id}`}>{c.number}</Link></td>{cust.multi && <td>{cust.of(c)}</td>}<td><b>{c.title}</b></td>
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
        <Field label="Application"><select value={f.service_id} onChange={set('service_id')}><option value="">None</option>{(services.data || []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
        <div />
        <Field label="Planned start"><input type="datetime-local" value={f.planned_start} onChange={set('planned_start')} /></Field>
        <Field label="Planned end"><input type="datetime-local" value={f.planned_end} onChange={set('planned_end')} /></Field>
        <Field label="Implementation plan" wide><textarea value={f.implementation_plan} onChange={set('implementation_plan')} /></Field>
        <Field label="Backout plan" wide><textarea value={f.backout_plan} onChange={set('backout_plan')} /></Field>
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
  const [tab, setTab] = useTab(['details', 'activity'])
  const [run, busy] = useAction()

  if (chg.loading && !chg.data) return <Loading />
  if (chg.error) return <><button className="back" onClick={() => navigate('/changes')}>‹ Back to changes</button><ErrorBox error={chg.error} /></>
  const c = chg.data
  const refresh = () => { chg.reload(); activity.reload(); refreshCounts() }
  const move = (to) => run(async () => { await api.post(`/changes/${id}/transition`, { to_status: to }); refresh() }, `Moved to ${to}.`)

  return (
    <>
      <button className="back" onClick={() => navigate('/changes')}>‹ Back to changes</button>
      <DetailTitle number={c.number} title={c.title} status={c.status} />
      <ChangeBar c={c} me={me} run={run} busy={busy} onDone={refresh} onStatus={(a) => move(a.to)} />
      <Workflow steps={STATUSES} current={c.status} />
      <div className="detail">
        <div className="card">
          <div className="tabs">
            {[['details', 'Details'], ['activity', 'Activity']].map(([k, label]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>)}
          </div>
          {tab === 'details' && <ChangeForm c={c} me={me} onSaved={refresh} />}
          {tab === 'activity' && (
            <div className="incident-activity">
              <NoteBox kind="changes" id={id} notes={false} onAdded={() => activity.reload()} />
              <Timeline events={activity.data} onChanged={() => activity.reload()} />
            </div>
          )}
        </div>
        <div>
          {c.status === 'Under Review' && c.can_manage && (
            <div className="side"><h4>Actions</h4>
              <div className="sideactions"><div className="note">Needs an implementation plan, backout plan and planned start before approval.</div></div>
            </div>
          )}
          <ApprovalBox approvals={c.approvals} canDecide={me.role === 'admin'} onChanged={refresh} />
        </div>
      </div>
    </>
  )
}

function ChangeForm({ c, me, onSaved }) {
  const canEdit = c.can_manage && c.status !== 'Closed' && (c.status === 'Draft' || me.role === 'admin')
  const initial = () => ({ implementation_plan: c.implementation_plan || '', test_plan: c.test_plan || '', backout_plan: c.backout_plan || '', planned_start: toInputDate(c.planned_start), planned_end: toInputDate(c.planned_end) })
  const [f, setF] = useState(initial)
  const [run, busy] = useAction()
  useEffect(() => setF(initial()), [c.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = (e) => {
    e.preventDefault()
    const init = initial(), changes = {}
    Object.keys(f).forEach((k) => {
      if (f[k] === init[k]) return
      changes[k] = k.startsWith('planned') ? fromInputDate(f[k]) : f[k]
    })
    if (!Object.keys(changes).length) return
    run(async () => { await api.patch(`/changes/${c.id}`, changes); onSaved() }, 'Change updated.')
  }
  return (
    <form className="form" onSubmit={save}>
      <Field label="Title" wide><Text value={c.title} /></Field>
      <Field label="Planned start">{canEdit ? <input type="datetime-local" value={f.planned_start} onChange={set('planned_start')} /> : <Text value={c.planned_start && fmtDate(c.planned_start)} />}</Field>
      <Field label="Planned end">{canEdit ? <input type="datetime-local" value={f.planned_end} onChange={set('planned_end')} /> : <Text value={c.planned_end && fmtDate(c.planned_end)} />}</Field>
      <Field label="Implementation plan" wide>{canEdit ? <textarea value={f.implementation_plan} onChange={set('implementation_plan')} /> : <Text value={c.implementation_plan} />}</Field>
      <Field label="Backout plan" wide>{canEdit ? <textarea value={f.backout_plan} onChange={set('backout_plan')} /> : <Text value={c.backout_plan} />}</Field>
      <Field label="Test plan" wide>{canEdit ? <textarea value={f.test_plan} onChange={set('test_plan')} /> : <Text value={c.test_plan} />}</Field>
      <Field label="Created"><Text value={fmtDate(c.created_at)} /></Field>
      {c.releases.length > 0 && <Field label="In releases"><div className="ro">{c.releases.map((r) => <div key={r.id}><Link className="link" to={`/releases/${r.id}`}>{r.number}</Link> {r.name}</div>)}</div></Field>}
      {canEdit && <div className="formactions"><button className="btn" disabled={busy}>Save changes</button></div>}
    </form>
  )
}

// Application, requester, type, risk and status as dropdowns across the top of the change.
function ChangeBar({ c, me, run, busy, onDone, onStatus }) {
  const services = useFetch(() => api.get('/services'))
  const canEdit = c.can_manage && c.status !== 'Closed' && (c.status === 'Draft' || me.role === 'admin')
  const patch = (changes, ok) => run(async () => { await api.patch(`/changes/${c.id}`, changes); onDone() }, ok)
  const apps = (services.data || []).filter((a) => a.active || a.id === c.service_id)
  return <FieldBar fields={[
    { label: 'Application', value: c.service_id || '', locked: !canEdit, disabled: busy, onChange: (v) => patch({ service_id: v || null }, 'Application updated.'),
      options: [{ value: '', label: 'None' }, ...apps.map((a) => ({ value: a.id, label: a.name }))] },
    { label: 'Requester', text: c.requester_name },
    { label: 'Type', value: c.type, locked: !canEdit, disabled: busy, onChange: (v) => patch({ type: v }, 'Type updated.'), options: TYPES.map((t) => ({ value: t, label: t })) },
    { label: 'Risk', value: c.risk, locked: !canEdit, disabled: busy, onChange: (v) => patch({ risk: v }, 'Risk updated.'), options: LEVELS.map((t) => ({ value: t, label: t })) },
    statusField({ status: c.status, actions: nextActions(c), busy, onPick: onStatus, none: c.status === 'Closed' ? 'This change is closed.' : 'No status changes are available to you.' }),
  ]} />
}

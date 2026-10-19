import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import {
  Empty, ErrorBox, Field, FormModal, Loading, PRIORITIES, Pager, PersonSelect, Priority, RecordPicker, StatusBadge, Text, Timeline,
  Workflow, fmtDate, useAction, useDebounced, useFetch,
} from '../components/ui'

const STATUSES = ['Identified', 'Investigating', 'Root Cause Identified', 'Fix Planned', 'Resolved', 'Closed']
const LIMIT = 25

export function ProblemList() {
  const { me } = useAuth()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [openOnly, setOpenOnly] = useState(false)
  const [offset, setOffset] = useState(0)
  const [sp, setSp] = useSearchParams()
  const [creating, setCreating] = useState(sp.get('new') === '1')
  useEffect(() => { if (sp.get('new')) { sp.delete('new'); setSp(sp, { replace: true }) } }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const dq = useDebounced(q)
  useEffect(() => setOffset(0), [dq, status, priority, openOnly])
  const { data, error, loading } = useFetch(
    () => api.get('/problems', { q: dq.trim(), status, priority, open_only: openOnly || undefined, limit: LIMIT, offset }),
    [dq, status, priority, openOnly, offset],
  )
  return (
    <>
      <div className="eyebrow">Problem Management</div>
      <h2 className="title">Problems & Known Errors</h2>
      <p className="sub">Investigate recurring incidents, root causes, workarounds and permanent fixes.{me.role === 'employee' && ' You see the problems you raised.'}</p>
      <div className="toolbar">
        <div className="filters">
          <input placeholder="Search problems" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search problems" />
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
          <select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority"><option value="">All priorities</option>{[...PRIORITIES].reverse().map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <label><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open only</label>
        </div>
        <button className="btn" onClick={() => setCreating(true)}>+ New Problem</button>
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Problem</th><th>Title</th><th>Service</th><th>Priority</th><th>Owner</th><th>Status</th><th>Related Incidents</th></tr></thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.id}>
                <td><Link className="link" to={`/problems/${p.id}`}>{p.number}</Link></td><td><b>{p.title}</b></td>
                <td>{p.service_name || '—'}</td><td><Priority p={p.priority} /></td><td>{p.owner_name || '—'}</td>
                <td><StatusBadge status={p.status} /></td><td>{p.related_incidents}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.items.length && <Empty>No problems match.</Empty>}
        {data && <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </div>
      {creating && <NewProblem onClose={() => setCreating(false)} onCreated={(p) => navigate(`/problems/${p.id}`)} />}
    </>
  )
}

function NewProblem({ onClose, onCreated }) {
  const { me } = useAuth()
  const services = useFetch(() => api.get('/services'))
  const [f, setF] = useState({ title: '', description: '', service_id: '', priority: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async () => {
    const body = { title: f.title }
    if (f.description) body.description = f.description
    if (f.service_id) body.service_id = f.service_id
    if (f.priority && me.role !== 'employee') body.priority = f.priority
    onCreated(await api.post('/problems', body))
  }
  return (
    <FormModal title="New Problem" submitLabel="Create problem" onClose={onClose} onSubmit={submit}>
      <div className="form">
        <Field label="Title" wide><input value={f.title} onChange={set('title')} minLength={3} maxLength={200} required autoFocus /></Field>
        <Field label="Service"><select value={f.service_id} onChange={set('service_id')}><option value="">Not sure / other</option>{(services.data || []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
        {me.role !== 'employee' && <Field label="Priority"><select value={f.priority} onChange={set('priority')}><option value="">Default (Medium)</option>{PRIORITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>}
        <Field label="Description / business impact" wide><textarea value={f.description} onChange={set('description')} /></Field>
      </div>
    </FormModal>
  )
}

function nextActions(p) {
  const map = {
    Identified: [{ label: 'Start investigation', to: 'Investigating', primary: true }],
    Investigating: [{ label: 'Root cause identified', to: 'Root Cause Identified', primary: true }],
    'Root Cause Identified': [{ label: 'Fix planned', to: 'Fix Planned', primary: true }],
    'Fix Planned': [{ label: 'Mark resolved', to: 'Resolved', primary: true }],
    Resolved: [{ label: 'Close problem', to: 'Closed', primary: true }, { label: 'Reopen investigation', to: 'Investigating' }],
  }
  return p.can_manage ? map[p.status] || [] : []
}

export function ProblemDetail() {
  const { id } = useParams()
  const { me } = useAuth()
  const navigate = useNavigate()
  const prob = useFetch(() => api.get(`/problems/${id}`), [id])
  const activity = useFetch(() => api.get(`/problems/${id}/activity`), [id])
  const assignable = useFetch(() => (prob.data?.can_manage ? api.get('/users/assignable') : []), [id, prob.data?.can_manage])
  const [tab, setTab] = useState('details')
  const [run, busy] = useAction()
  const [owner, setOwner] = useState('')

  if (prob.loading && !prob.data) return <Loading />
  if (prob.error) return <><button className="back" onClick={() => navigate('/problems')}>‹ Back to problems</button><ErrorBox error={prob.error} /></>
  const p = prob.data
  const refresh = () => { prob.reload(); activity.reload() }
  const move = (to) => run(async () => { await api.post(`/problems/${id}/transition`, { to_status: to }); refresh() }, `Moved to ${to}.`)
  const link = (inc) => run(async () => { await api.post(`/problems/${id}/incidents`, { incident_id: inc.id }); refresh() }, 'Incident linked.')
  const unlink = (inc) => run(async () => { await api.del(`/problems/${id}/incidents/${inc.id}`); refresh() }, 'Incident unlinked.')

  return (
    <>
      <button className="back" onClick={() => navigate('/problems')}>‹ Back to problems</button>
      <div className="dtitle"><h2>{p.number}</h2><StatusBadge status={p.status} /><Priority p={p.priority} /></div>
      <p className="sub">{p.title}</p>
      <Workflow steps={STATUSES} current={p.status} />
      <div className="detail">
        <div className="card">
          <div className="tabs">
            {[['details', 'Details'], ['incidents', `Related incidents (${p.related_incidents})`], ['activity', 'Activity']].map(([k, label]) => (
              <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>
          {tab === 'details' && <ProblemForm p={p} me={me} onSaved={refresh} />}
          {tab === 'incidents' && (
            <div style={{ padding: 15 }}>
              {p.can_manage && p.status !== 'Closed' && (
                <div style={{ marginBottom: 12 }}>
                  <RecordPicker path="/incidents" placeholder="Link an incident: type its number or description" label={(r) => r.short_description} onPick={link} />
                </div>
              )}
              {!p.incidents.length ? <Empty>No incidents linked yet.</Empty> : (
                <table style={{ minWidth: 0 }}>
                  <thead><tr><th>Incident</th><th>Description</th><th>Priority</th><th>Status</th><th /></tr></thead>
                  <tbody>{p.incidents.map((i) => (
                    <tr key={i.id}>
                      <td><Link className="link" to={`/incidents/${i.id}`}>{i.number}</Link></td><td>{i.short_description}</td>
                      <td><Priority p={i.priority} /></td><td><StatusBadge status={i.status} /></td>
                      <td>{p.can_manage && p.status !== 'Closed' && <button className="btn2" disabled={busy} onClick={() => unlink(i)}>Unlink</button>}</td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          )}
          {tab === 'activity' && <div className="incident-activity"><Timeline events={activity.data} /></div>}
        </div>
        <div>
          <div className="side">
            <h4>Summary</h4>
            {[['Service', p.service_name || '—'], ['Team', p.team_name || '—'], ['Raised by', p.raised_by_name], ['Owner', p.owner_name || 'Unassigned'],
              ['Related incidents', p.related_incidents], ['Created', fmtDate(p.created_at)]].map(([k, v]) => <div className="sr" key={k}><label>{k}</label><b>{v}</b></div>)}
          </div>
          {p.can_manage && p.status !== 'Closed' && (
            <div className="side">
              <h4>Actions</h4>
              <div className="sideactions">
                <PersonSelect people={assignable.data || []} value={owner} onChange={setOwner} placeholder={p.owner_name ? `Change owner (now ${p.owner_name})` : 'Assign an owner…'} />
                <button className="btn2" disabled={!owner || busy} onClick={() => run(async () => { await api.post(`/problems/${id}/assign`, { owner_id: owner }); setOwner(''); refresh() }, 'Owner updated.')}>Set owner</button>
                {nextActions(p).map((a) => <button key={a.label} className={a.primary ? 'btn' : 'btn2'} disabled={busy} onClick={() => move(a.to)}>{a.label}</button>)}
                {p.status === 'Investigating' && !p.root_cause && <div className="note">Fill in the root cause (Details tab) before marking it identified.</div>}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function ProblemForm({ p, me, onSaved }) {
  const services = useFetch(() => api.get('/services'))
  const staff = p.can_manage
  const canEdit = p.status !== 'Closed' && (staff || (p.raised_by === me.id && p.status === 'Identified'))
  const initial = () => ({ title: p.title, description: p.description || '', service_id: p.service_id || '', priority: p.priority, root_cause: p.root_cause || '', workaround: p.workaround || '', permanent_solution: p.permanent_solution || '' })
  const [f, setF] = useState(initial)
  const [run, busy] = useAction()
  useEffect(() => setF(initial()), [p.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = (e) => {
    e.preventDefault()
    const init = initial(), changes = {}
    Object.keys(f).forEach((k) => { if (f[k] !== init[k]) changes[k] = k === 'service_id' ? f[k] || null : f[k] })
    if (!Object.keys(changes).length) return
    run(async () => { await api.patch(`/problems/${p.id}`, changes); onSaved() }, 'Problem updated.')
  }
  const sEdit = staff && canEdit
  return (
    <form className="form" onSubmit={save}>
      <Field label="Title" wide>{canEdit ? <input value={f.title} onChange={set('title')} minLength={3} required /> : <Text value={p.title} />}</Field>
      <Field label="Service">{canEdit ? <select value={f.service_id} onChange={set('service_id')}><option value="">None</option>{(services.data || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select> : <Text value={p.service_name} />}</Field>
      <Field label="Priority">{sEdit ? <select value={f.priority} onChange={set('priority')}>{PRIORITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select> : <Priority p={p.priority} />}</Field>
      <Field label="Description / business impact" wide>{canEdit ? <textarea value={f.description} onChange={set('description')} /> : <Text value={p.description} />}</Field>
      <Field label="Root cause" wide>{sEdit ? <textarea value={f.root_cause} onChange={set('root_cause')} /> : <Text value={p.root_cause} />}</Field>
      <Field label="Workaround" wide>{sEdit ? <textarea value={f.workaround} onChange={set('workaround')} /> : <Text value={p.workaround} />}</Field>
      <Field label="Permanent solution" wide>{sEdit ? <textarea value={f.permanent_solution} onChange={set('permanent_solution')} /> : <Text value={p.permanent_solution} />}</Field>
      {canEdit && <div className="formactions"><button className="btn" disabled={busy}>Save changes</button></div>}
    </form>
  )
}

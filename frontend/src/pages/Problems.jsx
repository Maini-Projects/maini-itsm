import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ProjectFilter, useCustomers } from '../components/Customer'
import NoteBox from '../components/NoteBox'
import { urlParam,
  DetailTitle, FieldBar, statusField, Empty, ErrorBox, Field, FormModal, Loading, PRIORITIES, Pager, PersonSelect, Priority, RecordPicker, StatusBadge, Text, Timeline,
  Workflow, fmtDate, useAction, useDebounced, useFetch,
  useTab,
} from '../components/ui'
import CountPill from '../components/CountPill'

const STATUSES = ['Identified', 'Investigating', 'Root Cause Identified', 'Fix Planned', 'Resolved', 'Closed']
const LIMIT = 25

export function ProblemList() {
  const { me } = useAuth()
  const cust = useCustomers()
  const [projectId, setProjectId] = useState('')
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState(urlParam('status'))
  const [priority, setPriority] = useState(urlParam('priority'))
  const [openOnly, setOpenOnly] = useState(urlParam('open_only') === '1')
  const [offset, setOffset] = useState(0)
  const [sp, setSp] = useSearchParams()
  const [creating, setCreating] = useState(sp.get('new') === '1')
  useEffect(() => { if (sp.get('new')) { sp.delete('new'); setSp(sp, { replace: true }) } }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const dq = useDebounced(q)
  useEffect(() => setOffset(0), [dq, status, priority, openOnly, projectId])
  const { data, error, loading } = useFetch(
    () => api.get('/problems', { q: dq.trim(), status, priority, project_id: projectId || undefined, open_only: openOnly || undefined, limit: LIMIT, offset }),
    [dq, status, priority, openOnly, projectId, offset],
  )
  return (
    <>
      <div className="eyebrow">Problem Management <CountPill of="problems" /></div>
      <h2 className="title">Problems & Known Errors</h2>
      <div className="toolbar">
        <div className="filters">
          <ProjectFilter cust={cust} value={projectId} onChange={setProjectId} />
          <input placeholder="Search problems" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search problems" />
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">Status</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
          <select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority"><option value="">Priority</option>{[...PRIORITIES].reverse().map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <label><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open only</label>
        </div>
        <button className="btn" onClick={() => setCreating(true)}>+ New Problem</button>
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Problem</th>{cust.multi && <th>Project</th>}<th>Title</th><th>Application</th><th>Priority</th><th>Owner</th><th>Status</th><th>Related Incidents</th></tr></thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.id}>
                <td><Link className="link" to={`/problems/${p.id}`}>{p.number}</Link></td>{cust.multi && <td>{cust.of(p)}</td>}<td><b>{p.title}</b></td>
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
        <Field label="Application"><select value={f.service_id} onChange={set('service_id')}><option value="">Not sure / other</option>{(services.data || []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
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
  const [tab, setTab] = useTab(['details', 'incidents', 'activity'])
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
      <DetailTitle number={p.number} title={p.title} status={p.status} />
      <ProblemBar p={p} me={me} people={assignable.data || []} run={run} busy={busy} onDone={refresh} onStatus={(a) => move(a.to)} />
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
          {tab === 'activity' && (
            <div className="incident-activity">
              <NoteBox kind="problems" id={id} notes={false} onAdded={() => activity.reload()} />
              <Timeline events={activity.data} onChanged={() => activity.reload()} />
            </div>
          )}
        </div>
        <div>
          {p.can_manage && p.status !== 'Closed' && (
            <div className="side">
              <h4>Actions</h4>
              <div className="sideactions">
                <PersonSelect people={assignable.data || []} value={owner} onChange={setOwner} placeholder={p.owner_name ? `Change owner (now ${p.owner_name})` : 'Assign an owner…'} />
                <button className="btn2" disabled={!owner || busy} onClick={() => run(async () => { await api.post(`/problems/${id}/assign`, { owner_id: owner }); setOwner(''); refresh() }, 'Owner updated.')}>Set owner</button>
                {p.status === 'Investigating' && !p.root_cause && <div className="note">Fill in the root cause (Details tab) before moving it to Root Cause Identified.</div>}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function ProblemForm({ p, me, onSaved }) {
  const staff = p.can_manage
  const canEdit = p.status !== 'Closed' && (staff || (p.raised_by === me.id && p.status === 'Identified'))
  const initial = () => ({ root_cause: p.root_cause || '', workaround: p.workaround || '', permanent_solution: p.permanent_solution || '' })
  const [f, setF] = useState(initial)
  const [run, busy] = useAction()
  useEffect(() => setF(initial()), [p.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = (e) => {
    e.preventDefault()
    const init = initial(), changes = {}
    Object.keys(f).forEach((k) => { if (f[k] !== init[k]) changes[k] = f[k] })
    if (!Object.keys(changes).length) return
    run(async () => { await api.patch(`/problems/${p.id}`, changes); onSaved() }, 'Problem updated.')
  }
  const sEdit = staff && canEdit
  return (
    <form className="form" onSubmit={save}>
      <Field label="Title" wide><Text value={p.title} /></Field>
      <Field label="Description / business impact" wide><Text value={p.description} /></Field>
      <Field label="Root cause" wide>{sEdit ? <textarea value={f.root_cause} onChange={set('root_cause')} /> : <Text value={p.root_cause} />}</Field>
      <Field label="Workaround" wide>{sEdit ? <textarea value={f.workaround} onChange={set('workaround')} /> : <Text value={p.workaround} />}</Field>
      <Field label="Permanent solution" wide>{sEdit ? <textarea value={f.permanent_solution} onChange={set('permanent_solution')} /> : <Text value={p.permanent_solution} />}</Field>
      <Field label="Related incidents"><Text value={String(p.related_incidents)} /></Field>
      <Field label="Created"><Text value={fmtDate(p.created_at)} /></Field>
      {sEdit && <div className="formactions"><button className="btn" disabled={busy}>Save changes</button></div>}
    </form>
  )
}

// Application, raised by, owner, priority and status as dropdowns across the top of the problem.
function ProblemBar({ p, me, people, run, busy, onDone, onStatus }) {
  const services = useFetch(() => api.get('/services'))
  const staff = p.can_manage
  const canEdit = p.status !== 'Closed' && (staff || (p.raised_by === me.id && p.status === 'Identified'))
  const patch = (changes, ok) => run(async () => { await api.patch(`/problems/${p.id}`, changes); onDone() }, ok)
  const setOwner = (owner_id) => run(async () => { await api.post(`/problems/${p.id}/assign`, { owner_id }); onDone() }, 'Owner updated.')
  const apps = (services.data || []).filter((a) => a.active || a.id === p.service_id)
  return <FieldBar fields={[
    { label: 'Application', value: p.service_id || '', locked: !canEdit, disabled: busy, onChange: (v) => patch({ service_id: v || null }, 'Application updated.'),
      options: [{ value: '', label: 'None' }, ...apps.map((a) => ({ value: a.id, label: a.name }))] },
    { label: 'Raised by', text: p.raised_by_name },
    { label: 'Owner', value: p.owner_id || '', locked: !(staff && p.status !== 'Closed'), disabled: busy, onChange: (v) => v && setOwner(v),
      options: [...(p.owner_id ? [] : [{ value: '', label: 'Unassigned' }]),
        ...(p.owner_id && !people.some((x) => x.id === p.owner_id) ? [{ value: p.owner_id, label: p.owner_name }] : []),
        ...people.map((x) => ({ value: x.id, label: x.full_name }))] },
    { label: 'Priority', value: p.priority, locked: !(staff && canEdit), disabled: busy, onChange: (v) => patch({ priority: v }, 'Priority updated.'),
      options: PRIORITIES.map(([v, l]) => ({ value: v, label: l })) },
    statusField({ status: p.status, actions: nextActions(p), busy, onPick: onStatus, none: p.status === 'Closed' ? 'This problem is closed.' : 'No status changes are available to you.' }),
  ]} />
}

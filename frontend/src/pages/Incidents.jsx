import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import NoteBox from '../components/NoteBox'
import { urlParam,
  DetailTitle, FieldBar, statusField, Badge, Empty, ErrorBox, Field, FormModal, Loading, OpenFor, PRIORITIES, Pager, PersonSelect, Priority, StatusBadge, Text,
  Timeline, Workflow, fmtDate, roleLabel, useAction, useDebounced, useFetch,
  useTab,
} from '../components/ui'
import CountPill from '../components/CountPill'

const STATUSES = ['New', 'Assigned', 'In Progress', 'Pending', 'Resolved', 'Closed']
const LIMIT = 25

// ---- list ----------------------------------------------------------------------------------
export function IncidentList() {
  const { me } = useAuth()
  const navigate = useNavigate()
  const [sp, setSp] = useSearchParams()
  const [q, setQ] = useState(sp.get('q') || '')
  const [priority, setPriority] = useState(urlParam('priority'))
  const [status, setStatus] = useState(urlParam('status'))
  const [teamId, setTeamId] = useState('')
  const [openOnly, setOpenOnly] = useState(urlParam('open_only') === '1')
  const [serviceId, setServiceId] = useState(urlParam('service_id'))
  const [offset, setOffset] = useState(0)
  const [creating, setCreating] = useState(sp.get('new') === '1')
  const dq = useDebounced(q)
  const teams = useFetch(() => (me.role === 'admin' ? api.get('/teams') : []), [me.role])

  useEffect(() => { setQ(sp.get('q') || '') }, [sp])
  useEffect(() => setOffset(0), [dq, priority, status, teamId, openOnly, serviceId])

  const { data, error, loading } = useFetch(
    () => api.get('/incidents', { q: dq.trim(), priority, status, team_id: teamId, service_id: serviceId || undefined, open_only: openOnly || undefined, limit: LIMIT, offset }),
    [dq, priority, status, teamId, openOnly, serviceId, offset],
  )

  const created = useRef(null)
  const closeCreate = () => {
    setCreating(false)
    if (created.current) { navigate(`/incidents/${created.current.id}`); return } // go to the new incident
    if (sp.get('new')) { sp.delete('new'); setSp(sp, { replace: true }) }
  }

  return (
    <>
      <div className="eyebrow">Incident Management <CountPill of="incidents" /></div>
      <h2 className="title">Incidents</h2>
      <p className="sub">Create, assign, monitor, resolve and close operational incidents.{me.role === 'employee' && ' You see the incidents you raised.'}</p>
      <div className="toolbar">
        <div className="filters">
          <input placeholder="Search incidents" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search incidents" />
          <select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority">
            <option value="">All priorities</option>{[...PRIORITIES].reverse().map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          {me.role === 'admin' && (
            <select value={teamId} onChange={(e) => setTeamId(e.target.value)} aria-label="Team">
              <option value="">All teams</option>{(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          )}
          <label><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open only</label>
        </div>
        <button className="btn" onClick={() => setCreating(true)}>+ New Incident</button>
      </div>
      {serviceId && <div className="card" style={{ padding: '8px 12px', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
        Showing one application's incidents <button className="btn2" onClick={() => setServiceId('')}>Clear filter ✕</button>
      </div>}
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Incident</th><th>Short Description</th><th>Application</th><th>Priority</th><th>Team</th><th>Assignee</th><th>Status</th><th>Open For</th></tr></thead>
          <tbody>
            {data?.items.map((i) => (
              <tr key={i.id}>
                <td><Link className="link" to={`/incidents/${i.id}`}>{i.number}</Link></td>
                <td><b>{i.short_description}</b></td>
                <td>{i.service_name || '—'}</td><td><Priority p={i.priority} /></td><td>{i.team_name || '—'}</td>
                <td>{i.assignee_name || '—'}</td><td><StatusBadge status={i.status} /></td><td><OpenFor inc={i} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.items.length && <Empty>No incidents match.</Empty>}
        {data && <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </div>
      {creating && <NewIncident onClose={closeCreate} onCreated={(i) => { created.current = i }} />}
    </>
  )
}

function NewIncident({ onClose, onCreated }) {
  const { me } = useAuth()
  const services = useFetch(() => api.get('/services'))
  const people = useFetch(() => (me.role === 'admin' ? api.get('/users') : []), [me.role])
  const [f, setF] = useState({ short_description: '', description: '', service_id: '', priority: 'P3', requester_id: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async () => {
    const body = { ...f, service_id: f.service_id || null, requester_id: f.requester_id || null }
    if (!body.description) delete body.description
    onCreated(await api.post('/incidents', body))
  }
  return (
    <FormModal title="New Incident" submitLabel="Create incident" onClose={onClose} onSubmit={submit}>
      <div className="form">
        <Field label="Short description" wide><input value={f.short_description} onChange={set('short_description')} minLength={3} maxLength={200} required autoFocus /></Field>
        <Field label="Application">
          <select value={f.service_id} onChange={set('service_id')}>
            <option value="">Not sure / other</option>
            {(services.data || []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        {me.role === 'admin' && (
          <Field label="Raise on behalf of">
            <select value={f.requester_id} onChange={set('requester_id')}>
              <option value="">Myself</option>
              {(people.data || []).filter((p) => p.status === 'active').map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.team_name || roleLabel(p.role)})</option>)}
            </select>
          </Field>
        )}
        <Field label="Priority"><select value={f.priority} onChange={set('priority')}>{PRIORITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        <div />
        <Field label="Description" wide><textarea value={f.description} onChange={set('description')} /></Field>
      </div>
    </FormModal>
  )
}

// ---- detail --------------------------------------------------------------------------------
function nextActions(inc, me) {
  const out = []
  const staff = inc.can_manage
  if (staff) {
    if (inc.status === 'Assigned') out.push({ label: 'Start work', to: 'In Progress' })
    if (inc.status === 'In Progress') {
      out.push({ label: 'Put on hold', to: 'Pending' })
      out.push({ label: 'Resolve…', to: 'Resolved', notes: true, primary: true })
    }
    if (inc.status === 'Pending') out.push({ label: 'Resume work', to: 'In Progress' })
    if (inc.status === 'Resolved') {
      out.push({ label: 'Close incident', to: 'Closed', primary: true })
      out.push({ label: 'Reopen', to: 'In Progress' })
    }
  } else if (inc.requester_id === me.id && inc.status === 'Resolved') {
    out.push({ label: 'Confirm resolved (close)', to: 'Closed', primary: true })
    out.push({ label: 'Reopen — not fixed', to: 'In Progress' })
  }
  return out
}

export function IncidentDetail() {
  const { id } = useParams()
  const { me, refreshCounts } = useAuth()
  const navigate = useNavigate()
  const inc = useFetch(() => api.get(`/incidents/${id}`), [id])
  const activity = useFetch(() => api.get(`/incidents/${id}/activity`), [id])
  const assignable = useFetch(() => (inc.data?.can_manage ? api.get('/users/assignable') : []), [id, inc.data?.can_manage])
  const [tab, setTab] = useTab(['details', 'activity', 'resolution'])
  const [run, busy] = useAction()
  const [resolving, setResolving] = useState(null)

  if (inc.loading && !inc.data) return <Loading />
  if (inc.error) return <><button className="back" onClick={() => navigate('/incidents')}>‹ Back to incidents</button><ErrorBox error={inc.error} /></>
  const i = inc.data
  const refresh = () => { inc.reload(); activity.reload(); refreshCounts() }
  const move = (to, resolution_notes) => run(async () => { await api.post(`/incidents/${id}/transition`, { to_status: to, resolution_notes }); refresh() }, `Moved to ${to}.`)
  const steps = ['New', 'Assigned', 'In Progress', 'Resolved', 'Closed']
  const current = i.status === 'Pending' ? 'In Progress' : i.status
  const actions = nextActions(i, me)

  return (
    <>
      <button className="back" onClick={() => navigate('/incidents')}>‹ Back to incidents</button>
      <DetailTitle number={i.number} title={i.short_description} status={i.status} />
      <InfoBar inc={i} me={me} people={assignable.data || []} run={run} busy={busy} onDone={refresh}
        statusActions={actions} onStatus={(a) => (a.notes ? setResolving(a) : move(a.to))} />
      <Workflow steps={steps} current={current} />
      <div className="detail">
        <div className="card">
          <div className="tabs">
            {[['details', 'Details'], ['activity', 'Activity'], ['resolution', 'Resolution']].map(([k, label]) => (
              <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>
          {tab === 'details' && <DetailsForm inc={i} />}
          {tab === 'resolution' && (
            <div className="form"><Field label="Resolution notes" wide><Text value={i.resolution_notes} /></Field>
            </div>
          )}
          {tab === 'activity' && (
            <div className="incident-activity">
              <NoteBox kind="incidents" id={id} staff={i.can_manage} ownerLabel="requester" onAdded={() => activity.reload()} />
              <Timeline events={activity.data} onChanged={() => activity.reload()} />
            </div>
          )}
        </div>
        <div>
          {(i.can_manage || actions.length > 0) && i.status !== 'Closed' && (
            <div className="side">
              <h4>Actions</h4>
              <div className="sideactions">
                {i.can_manage && <AssignControl inc={i} people={assignable.data || []} run={run} busy={busy} onDone={refresh} />}
                {i.status === 'New' && i.can_manage && !i.assignee_id && <div className="note">Assign it to start work.</div>}
              </div>
            </div>
          )}
        </div>
      </div>
      {resolving && <ResolveModal onClose={() => setResolving(null)} onSubmit={(notes) => move('Resolved', notes)} />}
    </>
  )
}

function AssignControl({ inc, people, run, busy, onDone }) {
  const [who, setWho] = useState('')
  return (
    <>
      <PersonSelect people={people} value={who} onChange={setWho} placeholder={inc.assignee_name ? `Reassign (now ${inc.assignee_name})` : 'Assign to…'} />
      <button className="btn2" disabled={!who || busy}
        onClick={() => run(async () => { await api.post(`/incidents/${inc.id}/assign`, { assignee_id: who }); setWho(''); onDone() }, 'Assigned.')}>
        {inc.assignee_id ? 'Reassign' : 'Assign'}
      </button>
    </>
  )
}

function ResolveModal({ onClose, onSubmit }) {
  const [notes, setNotes] = useState('')
  return (
    <FormModal title="Resolve incident" submitLabel="Mark resolved" onClose={onClose} onSubmit={() => onSubmit(notes)} width={560}>
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label="Resolution notes"><textarea value={notes} onChange={(e) => setNotes(e.target.value)} required autoFocus /></Field>
      </div>
    </FormModal>
  )
}

const statusLabel = (s) => (s === 'Pending' ? 'Pending (on hold)' : s)

function DetailsForm({ inc }) {
  return (
    <div className="form">
      <Field label="Short description" wide><Text value={inc.short_description} /></Field>
      <Field label="Description" wide><Text value={inc.description} /></Field>
      <Field label="Open for"><div className="ro"><OpenFor inc={inc} /></div></Field>
      <Field label="Created"><Text value={fmtDate(inc.created_at)} /></Field>
      {inc.resolved_at && <Field label="Resolved"><Text value={fmtDate(inc.resolved_at)} /></Field>}
    </div>
  )
}

// Application, requester, assignee, priority and status as dropdowns across the top of the incident.
function InfoBar({ inc, me, people, run, busy, onDone, statusActions, onStatus }) {
  const services = useFetch(() => api.get('/services'))
  const staff = inc.can_manage
  const canEdit = inc.status !== 'Closed' && (staff || (inc.requester_id === me.id && inc.status === 'New'))
  const patch = (changes, ok) => run(async () => { await api.patch(`/incidents/${inc.id}`, changes); onDone() }, ok)
  const assign = (assignee_id) => run(async () => { await api.post(`/incidents/${inc.id}/assign`, { assignee_id }); onDone() }, 'Assigned.')
  const apps = (services.data || []).filter((a) => a.active || a.id === inc.service_id)
  const none = inc.status === 'Closed' ? 'This incident is closed.' : inc.status === 'New' && staff ? 'Assign it to start work.' : 'No status changes are available to you.'
  return <FieldBar fields={[
    { label: 'Application', value: inc.service_id || '', locked: !canEdit, disabled: busy, onChange: (v) => patch({ service_id: v || null }, 'Application updated.'),
      options: [{ value: '', label: 'None' }, ...apps.map((a) => ({ value: a.id, label: a.name }))] },
    { label: 'Requester', text: inc.requester_name },
    { label: 'Assignee', value: inc.assignee_id || '', locked: !(staff && inc.status !== 'Closed'), disabled: busy, onChange: (v) => v && assign(v),
      options: [...(inc.assignee_id ? [] : [{ value: '', label: 'Unassigned' }]),
        ...(inc.assignee_id && !people.some((x) => x.id === inc.assignee_id) ? [{ value: inc.assignee_id, label: inc.assignee_name }] : []),
        ...people.map((x) => ({ value: x.id, label: x.full_name }))] },
    { label: 'Priority', value: inc.priority, locked: !(staff && canEdit), disabled: busy, onChange: (v) => patch({ priority: v }, 'Priority updated.'),
      options: PRIORITIES.map(([v, l]) => ({ value: v, label: l })) },
    statusField({ status: inc.status, actions: statusActions, busy, onPick: onStatus, none, label: statusLabel }),
  ]} />
}

import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import {
  Badge, Empty, ErrorBox, Field, FormModal, Loading, Pager, PersonSelect, SeverityBadge, StatusBadge, Text,
  Timeline, Workflow, fmtDate, useAction, useDebounced, useFetch,
} from '../components/ui'

const STATUSES = ['New', 'Assigned', 'In Progress', 'Pending', 'Resolved', 'Closed']
const SEVERITIES = ['Critical', 'High', 'Medium', 'Low']
const ENVIRONMENTS = ['Production', 'UAT']
const LIMIT = 25

// ---- list ----------------------------------------------------------------------------------
export function DefectList() {
  const { me } = useAuth()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [severity, setSeverity] = useState('')
  const [environment, setEnvironment] = useState('')
  const [status, setStatus] = useState('')
  const [teamId, setTeamId] = useState('')
  const [openOnly, setOpenOnly] = useState(false)
  const [offset, setOffset] = useState(0)
  const [sp, setSp] = useSearchParams()
  const [creating, setCreating] = useState(sp.get('new') === '1')
  useEffect(() => { if (sp.get('new')) { sp.delete('new'); setSp(sp, { replace: true }) } }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const dq = useDebounced(q)
  const teams = useFetch(() => (me.role === 'admin' ? api.get('/teams') : []), [me.role])
  useEffect(() => setOffset(0), [dq, severity, environment, status, teamId, openOnly])

  const { data, error, loading } = useFetch(
    () => api.get('/defects', { q: dq.trim(), severity, environment, status, team_id: teamId, open_only: openOnly || undefined, limit: LIMIT, offset }),
    [dq, severity, environment, status, teamId, openOnly, offset],
  )

  const created = useRef(null)
  const closeCreate = () => {
    setCreating(false)
    if (created.current) navigate(`/defects/${created.current.id}`) // go to the new defect
  }

  return (
    <>
      <div className="eyebrow">Defect Management</div>
      <h2 className="title">Defects</h2>
      <p className="sub">Log, assign, track, fix and close defects found in a service.{me.role === 'employee' && ' You see the defects you raised.'}</p>
      <div className="toolbar">
        <div className="filters">
          <input placeholder="Search defects" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search defects" />
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severity">
            <option value="">All severities</option>{SEVERITIES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select value={environment} onChange={(e) => setEnvironment(e.target.value)} aria-label="Environment">
            <option value="">All environments</option>{ENVIRONMENTS.map((s) => <option key={s}>{s}</option>)}
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
        <button className="btn" onClick={() => setCreating(true)}>+ New Defect</button>
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Defect</th><th>Title</th><th>Service</th><th>Severity</th><th>Environment</th><th>Team</th><th>Assignee</th><th>Status</th></tr></thead>
          <tbody>
            {data?.items.map((d) => (
              <tr key={d.id}>
                <td><Link className="link" to={`/defects/${d.id}`}>{d.number}</Link></td>
                <td><b>{d.title}</b></td>
                <td>{d.service_name || '—'}</td><td><SeverityBadge severity={d.severity} /></td><td>{d.environment}</td>
                <td>{d.team_name || '—'}</td><td>{d.assignee_name || '—'}</td><td><StatusBadge status={d.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.items.length && <Empty>No defects match.</Empty>}
        {data && <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </div>
      {creating && <NewDefect onClose={closeCreate} onCreated={(d) => { created.current = d }} />}
    </>
  )
}

function NewDefect({ onClose, onCreated }) {
  const services = useFetch(() => api.get('/services'))
  const [f, setF] = useState({ title: '', service_id: '', severity: 'Medium', environment: 'Production', description: '', steps_to_reproduce: '', expected_result: '', actual_result: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async () => {
    const body = { title: f.title, severity: f.severity, environment: f.environment, service_id: f.service_id || null }
    ;['description', 'steps_to_reproduce', 'expected_result', 'actual_result'].forEach((k) => { if (f[k]) body[k] = f[k] })
    onCreated(await api.post('/defects', body))
  }
  return (
    <FormModal title="New Defect" submitLabel="Create defect" onClose={onClose} onSubmit={submit}>
      <div className="form">
        <Field label="Title" wide><input value={f.title} onChange={set('title')} minLength={3} maxLength={200} required autoFocus /></Field>
        <Field label="Service">
          <select value={f.service_id} onChange={set('service_id')}>
            <option value="">Not sure / other</option>
            {(services.data || []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Environment"><select value={f.environment} onChange={set('environment')}>{ENVIRONMENTS.map((l) => <option key={l}>{l}</option>)}</select></Field>
        <Field label="Severity" hint="How badly it affects users."><select value={f.severity} onChange={set('severity')}>{SEVERITIES.map((l) => <option key={l}>{l}</option>)}</select></Field>
        <div />
        <Field label="Description" wide><textarea value={f.description} onChange={set('description')} /></Field>
        <Field label="Steps to reproduce" wide><textarea value={f.steps_to_reproduce} onChange={set('steps_to_reproduce')} /></Field>
        <Field label="Expected result"><textarea value={f.expected_result} onChange={set('expected_result')} /></Field>
        <Field label="Actual result"><textarea value={f.actual_result} onChange={set('actual_result')} /></Field>
      </div>
    </FormModal>
  )
}

// ---- detail --------------------------------------------------------------------------------
function nextActions(d, me) {
  const out = []
  if (d.can_manage) {
    if (d.status === 'Assigned') out.push({ to: 'In Progress' })
    if (d.status === 'In Progress') {
      out.push({ to: 'Pending' })
      out.push({ to: 'Resolved', notes: true })
    }
    if (d.status === 'Pending') out.push({ to: 'In Progress' })
    if (d.status === 'Resolved') {
      out.push({ to: 'Closed' })
      out.push({ to: 'In Progress' })
    }
  } else if (d.raised_by === me.id && d.status === 'Resolved') {
    out.push({ to: 'Closed' })
    out.push({ to: 'In Progress' })
  }
  return out
}

export function DefectDetail() {
  const { id } = useParams()
  const { me, refreshCounts } = useAuth()
  const navigate = useNavigate()
  const def = useFetch(() => api.get(`/defects/${id}`), [id])
  const activity = useFetch(() => api.get(`/defects/${id}/activity`), [id])
  const assignable = useFetch(() => (def.data?.can_manage ? api.get('/users/assignable') : []), [id, def.data?.can_manage])
  const [tab, setTab] = useState('details')
  const [run, busy] = useAction()
  const [resolving, setResolving] = useState(false)

  if (def.loading && !def.data) return <Loading />
  if (def.error) return <><button className="back" onClick={() => navigate('/defects')}>‹ Back to defects</button><ErrorBox error={def.error} /></>
  const d = def.data
  const refresh = () => { def.reload(); activity.reload(); refreshCounts() }
  const move = (to, resolution_notes) => run(async () => { await api.post(`/defects/${id}/transition`, { to_status: to, resolution_notes }); refresh() }, `Moved to ${to}.`)
  const steps = ['New', 'Assigned', 'In Progress', 'Resolved', 'Closed']
  const current = d.status === 'Pending' ? 'In Progress' : d.status
  const actions = nextActions(d, me)

  return (
    <>
      <button className="back" onClick={() => navigate('/defects')}>‹ Back to defects</button>
      <div className="dtitle">
        <h2>{d.number}</h2><StatusBadge status={d.status} /><SeverityBadge severity={d.severity} />
        {d.status === 'Pending' && <Badge tone="gray">On hold</Badge>}
      </div>
      <p className="sub">{d.title}</p>
      <Workflow steps={steps} current={current} />
      <div className="detail">
        <div className="card">
          <div className="tabs">
            {[['details', 'Details'], ['activity', 'Activity'], ['resolution', 'Resolution']].map(([k, l]) => (
              <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>
          {tab === 'details' && <DetailsForm defect={d} me={me} onSaved={refresh} statusActions={actions} statusBusy={busy}
            onStatus={(a) => (a.notes ? setResolving(true) : move(a.to))} />}
          {tab === 'resolution' && (
            <div className="form"><Field label="Resolution notes" wide><Text value={d.resolution_notes} /></Field>
              {!d.resolution_notes && <div className="hint" style={{ gridColumn: '1/-1', fontSize: 12, color: 'var(--muted)' }}>Notes are added when staff resolve the defect.</div>}
            </div>
          )}
          {tab === 'activity' && (
            <div className="incident-activity">
              <NoteBox id={id} staff={d.can_manage} onAdded={() => activity.reload()} />
              <Timeline events={activity.data} />
            </div>
          )}
        </div>
        <div>
          <div className="side">
            <h4>Summary</h4>
            {[['Severity', <SeverityBadge key="s" severity={d.severity} />], ['Status', <StatusBadge key="st" status={d.status} />],
              ['Assignee', d.assignee_name || 'Unassigned'], ['Raised by', d.raised_by_name], ['Service', d.service_name || '—'],
              ['Environment', d.environment], ['Created', fmtDate(d.created_at)],
              ['Team', d.team_name || '—'], ['Resolved', fmtDate(d.resolved_at)]].map(([k, v]) => (
              <div className="sr" key={k}><label>{k}</label><b>{v}</b></div>
            ))}
          </div>
          {d.can_manage && d.status !== 'Closed' && (
            <div className="side">
              <h4>Actions</h4>
              <div className="sideactions">
                <AssignControl defect={d} people={assignable.data || []} run={run} busy={busy} onDone={refresh} />
                {d.status === 'New' && !d.assignee_id && <div className="note">Assign it to start work.</div>}
              </div>
            </div>
          )}
        </div>
      </div>
      {resolving && <ResolveModal onClose={() => setResolving(false)} onSubmit={(notes) => move('Resolved', notes)} />}
    </>
  )
}

function AssignControl({ defect, people, run, busy, onDone }) {
  const [who, setWho] = useState('')
  return (
    <>
      <PersonSelect people={people} value={who} onChange={setWho} placeholder={defect.assignee_name ? `Reassign (now ${defect.assignee_name})` : 'Assign to…'} />
      <button className="btn2" disabled={!who || busy}
        onClick={() => run(async () => { await api.post(`/defects/${defect.id}/assign`, { assignee_id: who }); setWho(''); onDone() }, 'Assigned.')}>
        {defect.assignee_id ? 'Reassign' : 'Assign'}
      </button>
    </>
  )
}

function ResolveModal({ onClose, onSubmit }) {
  const [notes, setNotes] = useState('')
  return (
    <FormModal title="Resolve defect" submitLabel="Mark resolved" onClose={onClose} onSubmit={() => onSubmit(notes)} width={560}>
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label="Resolution notes" hint="What was done to fix it. Required."><textarea value={notes} onChange={(e) => setNotes(e.target.value)} required autoFocus /></Field>
      </div>
    </FormModal>
  )
}

const statusLabel = (s) => (s === 'Pending' ? 'Pending (on hold)' : s)

function DetailsForm({ defect, me, onSaved, statusActions, statusBusy, onStatus }) {
  const services = useFetch(() => api.get('/services'))
  const staff = defect.can_manage
  const canEdit = defect.status !== 'Closed' && (staff || (defect.raised_by === me.id && defect.status === 'New'))
  const initial = () => ({
    title: defect.title, service_id: defect.service_id || '', severity: defect.severity, environment: defect.environment,
    description: defect.description || '', steps_to_reproduce: defect.steps_to_reproduce || '',
    expected_result: defect.expected_result || '', actual_result: defect.actual_result || '',
  })
  const [f, setF] = useState(initial)
  const [run, busy] = useAction()
  useEffect(() => setF(initial()), [defect.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = (e) => {
    e.preventDefault()
    const init = initial()
    const changes = {}
    Object.keys(f).forEach((k) => { if (f[k] !== init[k] && (staff || k !== 'severity')) changes[k] = k === 'service_id' ? f[k] || null : f[k] })
    if (!Object.keys(changes).length) return
    run(async () => { await api.patch(`/defects/${defect.id}`, changes); onSaved() }, 'Defect updated.')
  }
  const ro = !canEdit
  const svc = services.data || []
  return (
    <form className="form" onSubmit={save}>
      <Field label="Title" wide>{ro ? <Text value={defect.title} /> : <input value={f.title} onChange={set('title')} minLength={3} required />}</Field>
      <Field label="Service">{ro ? <Text value={defect.service_name} /> : <select value={f.service_id} onChange={set('service_id')}><option value="">None</option>{svc.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>}</Field>
      <Field label="Environment">{ro ? <Text value={defect.environment} /> : <select value={f.environment} onChange={set('environment')}>{ENVIRONMENTS.map((l) => <option key={l}>{l}</option>)}</select>}</Field>
      <Field label="Status" hint={statusActions.length === 0 ? (defect.status === 'Closed' ? 'This defect is closed.' : defect.status === 'New' && staff ? 'Assign it to start work.' : 'No status changes are available to you.') : 'Pick the next status to move it on.'}>
        <select value={defect.status} disabled={statusBusy || statusActions.length === 0}
          onChange={(e) => { const a = statusActions.find((x) => x.to === e.target.value); if (a) onStatus(a) }}>
          <option value={defect.status}>{statusLabel(defect.status)}</option>
          {[...new Map(statusActions.map((a) => [a.to, a])).values()].map((a) => <option key={a.to} value={a.to}>{statusLabel(a.to)}</option>)}
        </select>
      </Field>
      <Field label="Severity">{staff && canEdit ? <select value={f.severity} onChange={set('severity')}>{SEVERITIES.map((l) => <option key={l}>{l}</option>)}</select> : <Text value={defect.severity} />}</Field>
      <Field label="Description" wide>{ro ? <Text value={defect.description} /> : <textarea value={f.description} onChange={set('description')} />}</Field>
      <Field label="Steps to reproduce" wide>{ro ? <Text value={defect.steps_to_reproduce} /> : <textarea value={f.steps_to_reproduce} onChange={set('steps_to_reproduce')} />}</Field>
      <Field label="Expected result">{ro ? <Text value={defect.expected_result} /> : <textarea value={f.expected_result} onChange={set('expected_result')} />}</Field>
      <Field label="Actual result">{ro ? <Text value={defect.actual_result} /> : <textarea value={f.actual_result} onChange={set('actual_result')} />}</Field>
      {!ro && <div className="formactions"><button className="btn" disabled={busy}>Save changes</button></div>}
      {ro && defect.status !== 'Closed' && !staff && <div className="hint" style={{ gridColumn: '1/-1', fontSize: 11.5, color: 'var(--muted)' }}>You can edit your defect while it is New. After that, the team works on it — add a note in Activity to update them.</div>}
    </form>
  )
}

function NoteBox({ id, staff, onAdded }) {
  const [body, setBody] = useState('')
  const [internal, setInternal] = useState(false)
  const [run, busy] = useAction()
  const add = () => run(async () => { await api.post(`/defects/${id}/comments`, { body, internal: staff && internal }); setBody(''); setInternal(false); onAdded() }, 'Note added.')
  return (
    <div className="add-note-box" style={{ marginBottom: 16 }}>
      <label className="cap" htmlFor="defect-note">Add a note</label>
      <textarea id="defect-note" value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add an update or a question…" />
      <div className="add-note-actions">
        {staff ? <label className="checkrow"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note (hidden from the reporter)</label> : <span />}
        <button className="btn" disabled={!body.trim() || busy} onClick={add}>Add note</button>
      </div>
    </div>
  )
}

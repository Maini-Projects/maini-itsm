import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ProjectFilter, useCustomers } from '../components/Customer'
import NoteBox from '../components/NoteBox'
import { urlParam,
  DetailTitle, FieldBar, OpenFor, statusField, Badge, Empty, ErrorBox, Field, FormModal, Loading, Pager, PersonSelect, SeverityBadge, StatusBadge, Text,
  Timeline, Workflow, fmtDate, useAction, useDebounced, useFetch,
  useTab,
} from '../components/ui'
import CountPill from '../components/CountPill'

const STATUSES = ['New', 'Assigned', 'In Progress', 'Pending', 'Resolved', 'Closed']
const SEVERITIES = ['Critical', 'High', 'Medium', 'Low']
const ENVIRONMENTS = ['Production', 'UAT']
const LIMIT = 25

// ---- list ----------------------------------------------------------------------------------
export function DefectList() {
  const { me } = useAuth()
  const cust = useCustomers()
  const [projectId, setProjectId] = useState('')
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [severity, setSeverity] = useState(urlParam('severity'))
  const [environment, setEnvironment] = useState(urlParam('environment'))
  const [status, setStatus] = useState(urlParam('status'))
  const [teamId, setTeamId] = useState('')
  const [openOnly, setOpenOnly] = useState(urlParam('open_only') === '1')
  const [offset, setOffset] = useState(0)
  const [sp, setSp] = useSearchParams()
  const [creating, setCreating] = useState(sp.get('new') === '1')
  useEffect(() => { if (sp.get('new')) { sp.delete('new'); setSp(sp, { replace: true }) } }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const dq = useDebounced(q)
  const teams = useFetch(() => (me.role === 'admin' ? api.get('/teams') : []), [me.role])
  useEffect(() => setOffset(0), [dq, severity, environment, status, teamId, openOnly, projectId])

  const { data, error, loading } = useFetch(
    () => api.get('/defects', { q: dq.trim(), severity, environment, status, team_id: teamId, project_id: projectId || undefined, open_only: openOnly || undefined, limit: LIMIT, offset }),
    [dq, severity, environment, status, teamId, openOnly, projectId, offset],
  )

  const created = useRef(null)
  const closeCreate = () => {
    setCreating(false)
    if (created.current) navigate(`/defects/${created.current.id}`) // go to the new defect
  }

  return (
    <>
      <div className="eyebrow">Defect Management <CountPill of="defects" /></div>
      <h2 className="title">Defects</h2>
      <div className="toolbar">
        <div className="filters">
          <ProjectFilter cust={cust} value={projectId} onChange={setProjectId} />
          <input placeholder="Search defects" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search defects" />
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severity">
            <option value="">Severity</option>{SEVERITIES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select value={environment} onChange={(e) => setEnvironment(e.target.value)} aria-label="Environment">
            <option value="">Environment</option>{ENVIRONMENTS.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
            <option value="">Status</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          {me.role === 'admin' && (
            <select value={teamId} onChange={(e) => setTeamId(e.target.value)} aria-label="Team">
              <option value="">Team</option>{(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          )}
          <label><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open only</label>
        </div>
        <button className="btn" onClick={() => setCreating(true)}>+ New Defect</button>
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Defect</th>{cust.multi && <th>Project</th>}<th>Title</th><th>Application</th><th>Severity</th><th>Environment</th><th>Team</th><th>Assignee</th><th>Status</th></tr></thead>
          <tbody>
            {data?.items.map((d) => (
              <tr key={d.id}>
                <td><Link className="link" to={`/defects/${d.id}`}>{d.number}</Link></td>{cust.multi && <td>{cust.of(d)}</td>}
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
        <Field label="Application">
          <select value={f.service_id} onChange={set('service_id')}>
            <option value="">Not sure / other</option>
            {(services.data || []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Environment"><select value={f.environment} onChange={set('environment')}>{ENVIRONMENTS.map((l) => <option key={l}>{l}</option>)}</select></Field>
        <Field label="Severity"><select value={f.severity} onChange={set('severity')}>{SEVERITIES.map((l) => <option key={l}>{l}</option>)}</select></Field>
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
  const [tab, setTab] = useTab(['details', 'activity', 'resolution'])
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
      <DetailTitle number={d.number} title={d.title} status={d.status} />
      <DefectBar defect={d} me={me} people={assignable.data || []} run={run} busy={busy} onDone={refresh}
        statusActions={actions} onStatus={(a) => (a.notes ? setResolving(true) : move(a.to))} />
      <Workflow steps={steps} current={current} />
      <div className="detail">
        <div className="card">
          <div className="tabs">
            {[['details', 'Details'], ['activity', 'Activity'], ['resolution', 'Resolution']].map(([k, l]) => (
              <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>
          {tab === 'details' && <DetailsForm defect={d} />}
          {tab === 'resolution' && (
            <div className="form"><Field label="Resolution notes" wide><Text value={d.resolution_notes} /></Field>
            </div>
          )}
          {tab === 'activity' && (
            <div className="incident-activity">
              <NoteBox kind="defects" id={id} staff={d.can_manage} ownerLabel="reporter" onAdded={() => activity.reload()} />
              <Timeline events={activity.data} onChanged={() => activity.reload()} />
            </div>
          )}
        </div>
        <div>
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
        <Field label="Resolution notes"><textarea value={notes} onChange={(e) => setNotes(e.target.value)} required autoFocus /></Field>
      </div>
    </FormModal>
  )
}

const statusLabel = (s) => (s === 'Pending' ? 'Pending (on hold)' : s)

function DetailsForm({ defect }) {
  return (
    <div className="form">
      <Field label="Title" wide><Text value={defect.title} /></Field>
      <Field label="Environment" wide><Text value={defect.environment} /></Field>
      <Field label="Description" wide><Text value={defect.description} /></Field>
      <Field label="Steps to reproduce" wide><Text value={defect.steps_to_reproduce} /></Field>
      <Field label="Expected result"><Text value={defect.expected_result} /></Field>
      <Field label="Actual result"><Text value={defect.actual_result} /></Field>
      <Field label="Open for"><div className="ro"><OpenFor inc={defect} /></div></Field>
      <Field label="Created"><Text value={fmtDate(defect.created_at)} /></Field>
      {defect.resolved_at && <Field label="Resolved"><Text value={fmtDate(defect.resolved_at)} /></Field>}
    </div>
  )
}

// Application, reporter, assignee, severity and status as dropdowns across the top of the defect.
function DefectBar({ defect, me, people, run, busy, onDone, statusActions, onStatus }) {
  const services = useFetch(() => api.get('/services'))
  const staff = defect.can_manage
  const canEdit = defect.status !== 'Closed' && (staff || (defect.raised_by === me.id && defect.status === 'New'))
  const patch = (changes, ok) => run(async () => { await api.patch(`/defects/${defect.id}`, changes); onDone() }, ok)
  const assign = (assignee_id) => run(async () => { await api.post(`/defects/${defect.id}/assign`, { assignee_id }); onDone() }, 'Assigned.')
  const apps = (services.data || []).filter((a) => a.active || a.id === defect.service_id)
  const none = defect.status === 'Closed' ? 'This defect is closed.' : defect.status === 'New' && staff ? 'Assign it to start work.' : 'No status changes are available to you.'
  return <FieldBar fields={[
    { label: 'Application', value: defect.service_id || '', locked: !canEdit, disabled: busy, onChange: (v) => patch({ service_id: v || null }, 'Application updated.'),
      options: [{ value: '', label: 'None' }, ...apps.map((a) => ({ value: a.id, label: a.name }))] },
    { label: 'Raised by', text: defect.raised_by_name },
    { label: 'Assignee', value: defect.assignee_id || '', locked: !(staff && defect.status !== 'Closed'), disabled: busy, onChange: (v) => v && assign(v),
      options: [...(defect.assignee_id ? [] : [{ value: '', label: 'Unassigned' }]),
        ...(defect.assignee_id && !people.some((x) => x.id === defect.assignee_id) ? [{ value: defect.assignee_id, label: defect.assignee_name }] : []),
        ...people.map((x) => ({ value: x.id, label: x.full_name }))] },
    { label: 'Severity', value: defect.severity, locked: !(staff && canEdit), disabled: busy, onChange: (v) => patch({ severity: v }, 'Severity updated.'),
      options: SEVERITIES.map((l) => ({ value: l, label: l })) },
    statusField({ status: defect.status, actions: statusActions, busy, onPick: onStatus, none, label: statusLabel }),
  ]} />
}

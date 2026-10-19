import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import ApprovalBox from '../components/ApprovalBox'
import {
  Empty, ErrorBox, Field, FormModal, Loading, Pager, RecordPicker, RiskBadge, StatusBadge, Text, Timeline, Workflow, fmtDate,
  fmtShort, fromInputDate, toInputDate, useAction, useDebounced, useFetch,
} from '../components/ui'

const STATUSES = ['Planned', 'Under Review', 'Approved', 'Ready to Deploy', 'Deployment', 'Validated', 'Closed']
const LIMIT = 25

export function ReleaseList() {
  const { me } = useAuth()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [environment, setEnvironment] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [sp, setSp] = useSearchParams()
  const [creating, setCreating] = useState(sp.get('new') === '1' && me.role !== 'employee')
  useEffect(() => { if (sp.get('new')) { sp.delete('new'); setSp(sp, { replace: true }) } }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const dq = useDebounced(q)
  useEffect(() => setOffset(0), [dq, environment, status])
  const { data, error, loading } = useFetch(() => api.get('/releases', { q: dq.trim(), environment, status, limit: LIMIT, offset }), [dq, environment, status, offset])
  return (
    <>
      <div className="eyebrow">Release Management</div>
      <h2 className="title">Releases</h2>
      <p className="sub">Plan releases, group changes and track approval, deployment and validation. Managers raise releases; an admin approves them.{me.role === 'employee' && ' You have read-only access.'}</p>
      <div className="toolbar">
        <div className="filters">
          <input placeholder="Search releases" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search releases" />
          <select value={environment} onChange={(e) => setEnvironment(e.target.value)} aria-label="Environment"><option value="">All environments</option><option>Production</option><option>UAT</option></select>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
        </div>
        {me.role !== 'employee' ? <button className="btn" onClick={() => setCreating(true)}>+ New Release</button> : <span />}
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Release</th><th>Name</th><th>Service</th><th>Owner</th><th>Environment</th><th>Status</th><th>Deployment</th></tr></thead>
          <tbody>
            {data?.items.map((r) => (
              <tr key={r.id}>
                <td><Link className="link" to={`/releases/${r.id}`}>{r.number}</Link></td><td><b>{r.name}</b></td><td>{r.service_name || '—'}</td>
                <td>{r.owner_name}</td><td>{r.environment}</td><td><StatusBadge status={r.status} /></td><td>{fmtShort(r.deployment_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.items.length && <Empty>No releases match.</Empty>}
        {data && <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </div>
      {creating && <NewRelease onClose={() => setCreating(false)} onCreated={(r) => navigate(`/releases/${r.id}`)} />}
    </>
  )
}

function NewRelease({ onClose, onCreated }) {
  const services = useFetch(() => api.get('/services'))
  const [f, setF] = useState({ name: '', environment: 'Production', service_id: '', scope: '', rollback_plan: '', deployment_at: '' })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async () => {
    const body = { name: f.name, environment: f.environment, service_id: f.service_id || null, deployment_at: fromInputDate(f.deployment_at) }
    ;['scope', 'rollback_plan'].forEach((k) => { if (f[k]) body[k] = f[k] })
    onCreated(await api.post('/releases', body))
  }
  return (
    <FormModal title="New Release" submitLabel="Create release" onClose={onClose} onSubmit={submit}>
      <div className="form">
        <Field label="Name" wide><input value={f.name} onChange={set('name')} minLength={3} maxLength={200} required autoFocus /></Field>
        <Field label="Environment"><select value={f.environment} onChange={set('environment')}><option>Production</option><option>UAT</option></select></Field>
        <Field label="Service"><select value={f.service_id} onChange={set('service_id')}><option value="">None</option>{(services.data || []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
        <Field label="Deployment date"><input type="datetime-local" value={f.deployment_at} onChange={set('deployment_at')} /></Field>
        <div />
        <Field label="Scope" wide hint="Required before it can be sent for review."><textarea value={f.scope} onChange={set('scope')} /></Field>
        <Field label="Rollback plan" wide hint="Required before it can be sent for review."><textarea value={f.rollback_plan} onChange={set('rollback_plan')} /></Field>
      </div>
    </FormModal>
  )
}

function nextActions(r) {
  const map = {
    Planned: { label: 'Send for review', to: 'Under Review' },
    Approved: { label: 'Ready to deploy', to: 'Ready to Deploy' },
    'Ready to Deploy': { label: 'Start deployment', to: 'Deployment' },
    Deployment: { label: 'Mark validated', to: 'Validated' },
    Validated: { label: 'Close release', to: 'Closed' },
  }
  return r.can_manage && map[r.status] ? [{ ...map[r.status], primary: true }] : []
}

export function ReleaseDetail() {
  const { id } = useParams()
  const { me, refreshCounts } = useAuth()
  const navigate = useNavigate()
  const rel = useFetch(() => api.get(`/releases/${id}`), [id])
  const activity = useFetch(() => api.get(`/releases/${id}/activity`), [id])
  const [tab, setTab] = useState('details')
  const [run, busy] = useAction()

  if (rel.loading && !rel.data) return <Loading />
  if (rel.error) return <><button className="back" onClick={() => navigate('/releases')}>‹ Back to releases</button><ErrorBox error={rel.error} /></>
  const r = rel.data
  const refresh = () => { rel.reload(); activity.reload(); refreshCounts() }
  const move = (to) => run(async () => { await api.post(`/releases/${id}/transition`, { to_status: to }); refresh() }, `Moved to ${to}.`)
  const link = (c) => run(async () => { await api.post(`/releases/${id}/changes`, { change_id: c.id }); refresh() }, 'Change added.')
  const unlink = (c) => run(async () => { await api.del(`/releases/${id}/changes/${c.id}`); refresh() }, 'Change removed.')
  const linksOpen = r.can_manage && r.status !== 'Closed' && (r.status === 'Planned' || me.role === 'admin')

  return (
    <>
      <button className="back" onClick={() => navigate('/releases')}>‹ Back to releases</button>
      <div className="dtitle"><h2>{r.number}</h2><StatusBadge status={r.status} /></div>
      <p className="sub">{r.name}</p>
      <Workflow steps={STATUSES} current={r.status} />
      <div className="detail">
        <div className="card">
          <div className="tabs">
            {[['details', 'Details'], ['changes', `Changes (${r.changes.length})`], ['activity', 'Activity']].map(([k, label]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>)}
          </div>
          {tab === 'details' && <ReleaseForm r={r} me={me} onSaved={refresh} />}
          {tab === 'changes' && (
            <div style={{ padding: 15 }}>
              {linksOpen && <div style={{ marginBottom: 12 }}><RecordPicker path="/changes" placeholder="Add a change: type its number or title" label={(x) => x.title} onPick={link} /></div>}
              {!r.changes.length ? <Empty>No changes in this release yet.</Empty> : (
                <table style={{ minWidth: 0 }}>
                  <thead><tr><th>Change</th><th>Title</th><th>Risk</th><th>Status</th><th /></tr></thead>
                  <tbody>{r.changes.map((c) => (
                    <tr key={c.id}>
                      <td><Link className="link" to={`/changes/${c.id}`}>{c.number}</Link></td><td>{c.title}</td><td><RiskBadge risk={c.risk} /></td><td><StatusBadge status={c.status} /></td>
                      <td>{linksOpen && <button className="btn2" disabled={busy} onClick={() => unlink(c)}>Remove</button>}</td>
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
            {[['Environment', r.environment], ['Service', r.service_name || '—'], ['Team', r.team_name || '—'], ['Owner', r.owner_name],
              ['Deployment', fmtDate(r.deployment_at)], ['Changes', r.changes.length], ['Created', fmtDate(r.created_at)]].map(([k, v]) => <div className="sr" key={k}><label>{k}</label><b>{v}</b></div>)}
          </div>
          {nextActions(r).length > 0 && (
            <div className="side"><h4>Actions</h4>
              <div className="sideactions">
                {nextActions(r).map((a) => <button key={a.label} className="btn" disabled={busy} onClick={() => move(a.to)}>{a.label}</button>)}
                {r.status === 'Planned' && <div className="note">Needs scope, rollback plan and deployment date before review.</div>}
              </div>
            </div>
          )}
          <ApprovalBox approvals={r.approvals} canDecide={me.role === 'admin'} onChanged={refresh} />
        </div>
      </div>
    </>
  )
}

function ReleaseForm({ r, me, onSaved }) {
  const services = useFetch(() => api.get('/services'))
  const canEdit = r.can_manage && r.status !== 'Closed' && (r.status === 'Planned' || me.role === 'admin')
  const initial = () => ({ name: r.name, environment: r.environment, service_id: r.service_id || '', scope: r.scope || '', rollback_plan: r.rollback_plan || '', deployment_at: toInputDate(r.deployment_at) })
  const [f, setF] = useState(initial)
  const [run, busy] = useAction()
  useEffect(() => setF(initial()), [r.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = (e) => {
    e.preventDefault()
    const init = initial(), changes = {}
    Object.keys(f).forEach((k) => {
      if (f[k] === init[k]) return
      changes[k] = k === 'service_id' ? f[k] || null : k === 'deployment_at' ? fromInputDate(f[k]) : f[k]
    })
    if (!Object.keys(changes).length) return
    run(async () => { await api.patch(`/releases/${r.id}`, changes); onSaved() }, 'Release updated.')
  }
  return (
    <form className="form" onSubmit={save}>
      <Field label="Name" wide>{canEdit ? <input value={f.name} onChange={set('name')} minLength={3} required /> : <Text value={r.name} />}</Field>
      <Field label="Environment">{canEdit ? <select value={f.environment} onChange={set('environment')}><option>Production</option><option>UAT</option></select> : <Text value={r.environment} />}</Field>
      <Field label="Service">{canEdit ? <select value={f.service_id} onChange={set('service_id')}><option value="">None</option>{(services.data || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select> : <Text value={r.service_name} />}</Field>
      <Field label="Deployment date">{canEdit ? <input type="datetime-local" value={f.deployment_at} onChange={set('deployment_at')} /> : <Text value={r.deployment_at && fmtDate(r.deployment_at)} />}</Field>
      <div />
      <Field label="Scope" wide>{canEdit ? <textarea value={f.scope} onChange={set('scope')} /> : <Text value={r.scope} />}</Field>
      <Field label="Rollback plan" wide>{canEdit ? <textarea value={f.rollback_plan} onChange={set('rollback_plan')} /> : <Text value={r.rollback_plan} />}</Field>
      {canEdit && <div className="formactions"><button className="btn" disabled={busy}>Save changes</button></div>}
      {!canEdit && r.status !== 'Closed' && <div className="hint" style={{ gridColumn: '1/-1', fontSize: 11.5, color: 'var(--muted)' }}>A release can be edited while it is Planned (admins can edit until it is closed).</div>}
    </form>
  )
}

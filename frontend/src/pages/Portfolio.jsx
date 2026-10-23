import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Field, FormModal, Loading, fmtShort, fmtTarget, priorityLabel, useFetch, useToast } from '../components/ui'

const LEVELS = ['High', 'Medium', 'Low']

// ---- services ------------------------------------------------------------------------------
export function Services() {
  const { me } = useAuth()
  const admin = me.role === 'admin'
  const { data, error, loading, reload } = useFetch(() => api.get('/services'))
  const [edit, setEdit] = useState(null) // null | 'new' | service
  return (
    <>
      <div className="eyebrow">Administration</div>
      <h2 className="title">Applications</h2>
      <div className="toolbar"><span />{admin && <button className="btn" onClick={() => setEdit('new')}>+ New Application</button>}</div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Application name</th><th>Details</th><th>Created</th>{admin && <th />}</tr></thead>
          <tbody>
            {data?.map((s) => (
              <tr key={s.id} style={{ opacity: s.active ? 1 : 0.6 }}>
                <td><b>{s.name}</b>{!s.active && <> <Badge tone="gray">Inactive</Badge></>}</td>
                <td>{s.description || '—'}</td>
                <td>{fmtShort(s.created_at)}</td>
                {admin && <td><button className="btn2" onClick={() => setEdit(s)}>Edit</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.length && <div className="empty">No applications yet.</div>}
      </div>
      {edit && <ServiceModal service={edit === 'new' ? null : edit} onClose={() => setEdit(null)} onSaved={reload} />}
    </>
  )
}

function ServiceModal({ service, onClose, onSaved }) {
  const toast = useToast()
  const teams = useFetch(() => api.get('/teams'))
  const [f, setF] = useState({ name: service?.name || '', description: service?.description || '', owner_team_id: service?.owner_team_id || '', criticality: service?.criticality || 'Medium', active: service ? service.active : true })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const submit = async () => {
    const body = { ...f, owner_team_id: f.owner_team_id || null, description: f.description || null }
    if (service) await api.patch(`/services/${service.id}`, body)
    else await api.post('/services', body)
    toast(service ? 'Application updated.' : 'Application created.')
    onSaved()
  }
  return (
    <FormModal title={service ? 'Edit application' : 'New application'} onClose={onClose} onSubmit={submit} width={560}>
      <div className="form">
        <Field label="Application name" wide><input value={f.name} onChange={set('name')} required autoFocus /></Field>
        <Field label="Owner team"><select value={f.owner_team_id} onChange={set('owner_team_id')}><option value="">None</option>{(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
        <Field label="Criticality"><select value={f.criticality} onChange={set('criticality')}>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select></Field>
        <Field label="Details" wide><textarea value={f.description} onChange={set('description')} /></Field>
        <Field label="Status"><label className="checkrow"><input type="checkbox" checked={f.active} onChange={set('active')} /> Active (can be chosen on new records)</label></Field>
      </div>
    </FormModal>
  )
}

// ---- SLA -----------------------------------------------------------------------------------
export function Sla() {
  const { me } = useAuth()
  const sla = useFetch(() => api.get('/sla'))
  const summary = useFetch(() => api.get('/dashboard/summary'))
  const [edit, setEdit] = useState(null)
  const perf = Object.fromEntries((summary.data?.sla_performance || []).map((p) => [p.priority, p]))
  const resolved = (summary.data?.sla_performance || []).reduce((a, p) => a + p.resolved_this_month, 0)
  const within = (summary.data?.sla_performance || []).reduce((a, p) => a + p.within_sla, 0)
  return (
    <>
      <div className="eyebrow">SLA Management</div>
      <h2 className="title">SLA Policies & Performance</h2>
      <ErrorBox error={sla.error || summary.error} />
      {(sla.loading || summary.loading) && <Loading />}
      {sla.data && summary.data && (
        <>
          <div className="kpis">
            {sla.data.map((p) => (
              <div className="kpi" key={p.priority}>
                <label>{priorityLabel(p.priority)} Response</label><b>{fmtTarget(p.response_minutes)}</b><small>Resolution {fmtTarget(p.resolution_minutes)}</small>
              </div>
            ))}
            <div className="kpi"><label>Compliance (month)</label><b>{resolved ? `${Math.round((100 * within) / resolved)}%` : '—'}</b><small>{resolved} resolved this month</small></div>
            <div className="kpi"><label>Breached now</label><b style={{ color: 'var(--red)' }}>{summary.data.incidents.sla_breached}</b><small>Open past resolution target</small></div>
          </div>
          <div className="card table">
            <table style={{ minWidth: 0 }}>
              <thead><tr><th>Priority</th><th>Response target</th><th>Resolution target</th><th>Resolved this month</th><th>Within SLA</th><th>Compliance</th>{me.role === 'admin' && <th />}</tr></thead>
              <tbody>
                {sla.data.map((p) => {
                  const r = perf[p.priority]
                  return (
                    <tr key={p.priority}>
                      <td><b>{priorityLabel(p.priority)}</b></td><td>{fmtTarget(p.response_minutes)}</td><td>{fmtTarget(p.resolution_minutes)}</td>
                      <td>{r?.resolved_this_month ?? 0}</td><td>{r?.within_sla ?? 0}</td><td>{r?.percent == null ? '—' : `${r.percent}%`}</td>
                      {me.role === 'admin' && <td><button className="btn2" onClick={() => setEdit(p)}>Edit</button></td>}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      {edit && <SlaModal policy={edit} onClose={() => setEdit(null)} onSaved={() => { sla.reload(); summary.reload() }} />}
    </>
  )
}

function SlaModal({ policy, onClose, onSaved }) {
  const toast = useToast()
  const [resp, setResp] = useState(policy.response_minutes)
  const [reso, setReso] = useState(policy.resolution_minutes)
  const submit = async () => {
    await api.put(`/sla/${policy.priority}`, { response_minutes: Number(resp), resolution_minutes: Number(reso) })
    toast(`${priorityLabel(policy.priority)} targets updated.`)
    onSaved()
  }
  return (
    <FormModal title={`Edit ${priorityLabel(policy.priority)} targets`} onClose={onClose} onSubmit={submit} width={480}>
      <div className="form">
        <Field label="Response (minutes)"><input type="number" min="1" value={resp} onChange={(e) => setResp(e.target.value)} required /></Field>
        <Field label="Resolution (minutes)"><input type="number" min="1" value={reso} onChange={(e) => setReso(e.target.value)} required /></Field>
      </div>
    </FormModal>
  )
}

import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Field, FormModal, Loading, fmtTarget, useFetch, useToast } from '../components/ui'

const LEVELS = ['High', 'Medium', 'Low']

// ---- services ------------------------------------------------------------------------------
export function Services() {
  const { me } = useAuth()
  const { data, error, loading, reload } = useFetch(() => api.get('/services'))
  const [edit, setEdit] = useState(null) // null | 'new' | service
  return (
    <>
      <div className="eyebrow">Projects & Services</div>
      <h2 className="title">Supported Projects and Services</h2>
      <p className="sub">Ownership, criticality and live incident counts for each supported service.</p>
      {me.role === 'admin' && <div className="toolbar"><span /><button className="btn" onClick={() => setEdit('new')}>+ New Service</button></div>}
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      <div className="reports">
        {data?.map((s) => (
          <div className="report" key={s.id} style={{ cursor: me.role === 'admin' ? 'pointer' : 'default', opacity: s.active ? 1 : 0.6 }} onClick={() => me.role === 'admin' && setEdit(s)}>
            <b>{s.name} {!s.active && <Badge tone="gray">Inactive</Badge>}</b>
            <span>{s.description || 'No description'}</span>
            <span>{s.owner_team_name || 'No owner team'} · {s.criticality} criticality · {s.open_incidents} open incident{Number(s.open_incidents) === 1 ? '' : 's'}</span>
          </div>
        ))}
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
    toast(service ? 'Service updated.' : 'Service created.')
    onSaved()
  }
  return (
    <FormModal title={service ? 'Edit service' : 'New service'} onClose={onClose} onSubmit={submit} width={560}>
      <div className="form">
        <Field label="Name" wide><input value={f.name} onChange={set('name')} required autoFocus /></Field>
        <Field label="Owner team"><select value={f.owner_team_id} onChange={set('owner_team_id')}><option value="">None</option>{(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
        <Field label="Criticality"><select value={f.criticality} onChange={set('criticality')}>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select></Field>
        <Field label="Description" wide><textarea value={f.description} onChange={set('description')} /></Field>
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
      <p className="sub">Response and resolution targets by priority, and how well they are being met this month.</p>
      <ErrorBox error={sla.error || summary.error} />
      {(sla.loading || summary.loading) && <Loading />}
      {sla.data && summary.data && (
        <>
          <div className="kpis">
            {sla.data.map((p) => (
              <div className="kpi" key={p.priority}>
                <label>{p.priority} Response</label><b>{fmtTarget(p.response_minutes)}</b><small>Resolution {fmtTarget(p.resolution_minutes)}</small>
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
                      <td><b>{p.priority}</b></td><td>{fmtTarget(p.response_minutes)}</td><td>{fmtTarget(p.resolution_minutes)}</td>
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
    toast(`${policy.priority} targets updated.`)
    onSaved()
  }
  return (
    <FormModal title={`Edit ${policy.priority} targets`} onClose={onClose} onSubmit={submit} width={480}>
      <div className="form">
        <Field label="Response (minutes)" hint={`= ${fmtTarget(Number(resp) || 0)}`}><input type="number" min="1" value={resp} onChange={(e) => setResp(e.target.value)} required /></Field>
        <Field label="Resolution (minutes)" hint={`= ${fmtTarget(Number(reso) || 0)}`}><input type="number" min="1" value={reso} onChange={(e) => setReso(e.target.value)} required /></Field>
        <div className="hint" style={{ gridColumn: '1/-1', fontSize: 11.5, color: 'var(--muted)' }}>New targets apply to incidents raised or re-prioritised from now on.</div>
      </div>
    </FormModal>
  )
}

import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Loading, StatusBadge, fmtShort, useFetch } from '../components/ui'

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
const sum = (o) => (o ? Object.values(o).reduce((a, b) => a + b, 0) : 0)

function Kpi({ label, value, note, to, color }) {
  const nav = useNavigate()
  return (
    <button className="kpi click" onClick={() => nav(to)}>
      <label>{label}</label><b style={color ? { color } : undefined}>{value}</b><small>{note}</small>
    </button>
  )
}

function SlaCard({ rows, to }) {
  return (
    <div className="card">
      <div className="head"><h3>SLA Performance (this month)</h3>{to && <Link className="btn2" to={to}>SLA details</Link>}</div>
      <div className="body">
        {rows.map((r) => (
          <div className="metric" key={r.priority}>
            <span>{r.priority} Resolution</span>
            <div className="prog"><i style={{ width: `${r.percent ?? 0}%` }} /></div>
            <b>{r.percent === null ? '—' : `${r.percent}%`}</b>
          </div>
        ))}
        <small style={{ color: 'var(--muted)', fontSize: 11 }}>Share of incidents resolved within their target. “—” means none resolved yet this month.</small>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { me } = useAuth()
  const { data: d, error, loading } = useFetch(() => api.get('/dashboard/summary'))
  const mine = useFetch(() => (me.role === 'employee' ? api.get('/incidents', { limit: 5 }) : null), [me.role])
  const staff = me.role !== 'employee'

  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const inc = d.incidents
  const activeProblems = sum(d.problems)
  const maxOpen = Math.max(1, ...d.team_workload.map((t) => t.open))

  return (
    <>
      <div className="dashboard-title-row">
        <h2 className="title">IT Operations Smart Dashboard</h2>
        {me.organization_name && <div className="project-name"><span className="project-label">Project</span><strong>{me.organization_name}</strong></div>}
      </div>
      <p className="sub">
        {staff ? (me.role === 'admin' ? 'Operational status across all teams.' : `Operational status for the ${me.team_name} team.`) : 'Your incidents and their progress.'}
      </p>
      <div className="major-action-only"><Link className="danger" to="/incidents?new=1">Open Incident</Link></div>

      {staff ? (
        <div className="kpis">
          <Kpi label="Open Incidents" value={inc.open} note={me.role === 'admin' ? 'Across all teams' : 'In your team'} to="/incidents" />
          <Kpi label="P1 / P2 Incidents" value={inc.p1_p2_open} color="var(--red)" note={`${inc.p1_open} critical · ${inc.p2_open} high`} to="/incidents" />
          <Kpi label="SLA At Risk" value={inc.sla_at_risk} color="var(--amber)" note={`${inc.sla_breached} breached · ${inc.due_within_30_min} due within 30 min`} to="/incidents" />
          <Kpi label="Pending Approvals" value={d.pending_approvals.total} note={`${plural(d.pending_approvals.change, 'change')} · ${plural(d.pending_approvals.release, 'release')} · ${plural(d.pending_approvals.incident, 'incident')}`} to="/approvals" />
          <Kpi label="Active Problems" value={activeProblems} note={`${d.problems['Root Cause Identified'] || 0} root causes identified`} to="/problems" />
          <Kpi label="Upcoming Releases" value={d.releases.upcoming_14_days} note="Next 14 days" to="/releases" />
        </div>
      ) : (
        <div className="kpis four">
          <Kpi label="My Open Incidents" value={inc.open} note="Raised by you" to="/incidents" />
          <Kpi label="P1 / P2 Incidents" value={inc.p1_p2_open} color="var(--red)" note={`${inc.p1_open} critical · ${inc.p2_open} high`} to="/incidents" />
          <Kpi label="SLA At Risk" value={inc.sla_at_risk} color="var(--amber)" note={`${inc.sla_breached} breached`} to="/incidents" />
          <Kpi label="Awaiting Sign-off" value={inc.awaiting_approval} note="Resolved, pending approval" to="/incidents" />
        </div>
      )}

      {staff ? (
        <div className="grid2">
          <div className="card">
            <div className="head"><h3>Team Workload</h3><Link className="btn2" to="/incidents">View tickets</Link></div>
            <div className="body">
              {d.team_workload.length === 0 ? 'No teams yet.' : (
                <div className="teams" style={{ gridTemplateColumns: `repeat(${Math.min(4, d.team_workload.length)},1fr)` }}>
                  {d.team_workload.map((t) => (
                    <div className="team" key={t.id}>
                      <b>{t.name}</b><span>{t.open} open · {t.at_risk} at risk</span>
                      <div className="prog" style={{ marginTop: 8 }}><i style={{ width: `${Math.round((100 * t.open) / maxOpen)}%` }} /></div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          <SlaCard rows={d.sla_performance} to={me.menu.includes('sla') ? '/sla' : null} />
        </div>
      ) : (
        <div className="grid2">
          <div className="card">
            <div className="head"><h3>My Recent Incidents</h3><Link className="btn2" to="/incidents">View all</Link></div>
            <div className="body">
              {mine.loading ? 'Loading…' : !mine.data?.items.length ? 'You have not raised any incidents yet.' : mine.data.items.map((i) => (
                <div key={i.id}><Link className="link" to={`/incidents/${i.id}`}>{i.number}</Link> · {i.short_description} <StatusBadge status={i.status} /></div>
              ))}
            </div>
          </div>
          <SlaCard rows={d.sla_performance} />
        </div>
      )}

      {staff && (
        <div className="grid3">
          <div className="card">
            <div className="head"><h3>Change Pipeline</h3><Badge tone="blue">{d.changes.active} active</Badge></div>
            <div className="body">{d.changes.approval_pending} approval pending · {d.changes.scheduled} scheduled · {d.changes.emergency} emergency</div>
          </div>
          <div className="card">
            <div className="head"><h3>Problem Health</h3><Badge tone="amber">{activeProblems} active</Badge></div>
            <div className="body">
              {activeProblems === 0 ? 'No active problems.' : Object.entries(d.problems).map(([s, n]) => <div key={s}>{n} {s.toLowerCase()}</div>)}
            </div>
          </div>
          <div className="card">
            <div className="head"><h3>Upcoming Releases</h3><Badge tone="green">{d.releases.upcoming_14_days} planned</Badge></div>
            <div className="body">
              {d.releases.next.length === 0 ? 'Nothing scheduled in the next 14 days.' : d.releases.next.map((r) => (
                <div key={r.id}><Link className="link" to={`/releases/${r.id}`}>{r.number}</Link> {r.name} · {fmtShort(r.deployment_at)}</div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

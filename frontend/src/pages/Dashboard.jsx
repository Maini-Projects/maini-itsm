import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Loading, StatusBadge, fmtShort, priorityLabel, useFetch } from '../components/ui'

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
const sum = (o) => (o ? Object.values(o).reduce((a, b) => a + b, 0) : 0)

const REQUEST_TYPES = [
  { to: '/incidents', label: 'Incident', hint: 'Something is broken or not working' },
  { to: '/problems', label: 'Problem', hint: 'Find the root cause of repeated incidents' },
  { to: '/defects', label: 'Defect', hint: 'A bug found in an application' },
  { to: '/changes', label: 'Change', hint: 'Request a change to an application', staff: true },
  { to: '/releases', label: 'Release', hint: 'Plan a release of changes', staff: true },
]

// "+ New Request": pick what you want to raise, then the form for it opens.
function NewRequestMenu({ role }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const box = useRef(null)
  useEffect(() => {
    const close = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const types = REQUEST_TYPES.filter((t) => !t.staff || role !== 'employee')
  return (
    <div className="reqmenu" ref={box}>
      <button className="danger" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>+ New Request ▾</button>
      {open && (
        <div className="menu" role="menu">
          {types.map((t) => (
            <button key={t.to} role="menuitem" onClick={() => { setOpen(false); navigate(`${t.to}?new=1`) }}>
              <b>{t.label}</b><small>{t.hint}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

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
            <span>{priorityLabel(r.priority)} Resolution</span>
            <div className="prog"><i style={{ width: `${r.percent ?? 0}%` }} /></div>
            <b>{r.percent === null ? '—' : `${r.percent}%`}</b>
          </div>
        ))}
      </div>
    </div>
  )
}

function KnowledgeCard() {
  const { data, loading } = useFetch(() => api.get('/kb', { limit: 5 }))
  return (
    <div className="card" style={{ marginTop: 15 }}>
      <div className="head"><h3>Knowledge base</h3><Link className="btn2" to="/kb">View all</Link></div>
      {loading && !data ? <Loading /> : !data?.items.length ? (
        <div className="kb-empty">
          <svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z" /><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5" /><path d="M9 8h7M9 12h5" /></svg>
          <b>No articles yet</b>
          <span>Guides and answers to common questions will appear here.</span>
        </div>
      ) : (
        <div className="body">
          {data.items.map((a) => <div key={a.id}><Link className="link" to={`/kb/${a.id}`}>{a.title}</Link>{a.category && <> <Badge tone="blue">{a.category}</Badge></>}</div>)}
        </div>
      )}
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
      <div className="major-action-only"><NewRequestMenu role={me.role} /></div>

      {staff ? (
        <div className="kpis">
          <Kpi label="Open Incidents" value={inc.open} note={me.role === 'admin' ? 'Across all teams' : 'In your team'} to="/incidents" />
          <Kpi label="Critical / High Incidents" value={inc.p1_p2_open} color="var(--red)" note={`${inc.p1_open} critical · ${inc.p2_open} high`} to="/incidents" />
          <Kpi label="SLA At Risk" value={inc.sla_at_risk} color="var(--amber)" note={`${inc.sla_breached} breached · ${inc.due_within_30_min} due within 30 min`} to="/incidents" />
          <Kpi label="Pending Approvals" value={d.pending_approvals.total} note={`${plural(d.pending_approvals.change, 'change')} · ${plural(d.pending_approvals.release, 'release')}`} to="/approvals" />
          <Kpi label="Active Problems" value={activeProblems} note={`${d.problems['Root Cause Identified'] || 0} root causes identified`} to="/problems" />
          <Kpi label="Upcoming Releases" value={d.releases.upcoming_14_days} note="Next 14 days" to="/releases" />
        </div>
      ) : (
        <div className="kpis four">
          <Kpi label="My Open Incidents" value={inc.open} note="Raised by you" to="/incidents" />
          <Kpi label="Critical / High Incidents" value={inc.p1_p2_open} color="var(--red)" note={`${inc.p1_open} critical · ${inc.p2_open} high`} to="/incidents" />
          <Kpi label="SLA At Risk" value={inc.sla_at_risk} color="var(--amber)" note={`${inc.sla_breached} breached`} to="/incidents" />
          <Kpi label="Resolved This Month" value={d.sla_performance.reduce((n, r) => n + r.resolved_this_month, 0)} note="Your incidents" to="/incidents" />
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

            <KnowledgeCard />
    </>
  )
}

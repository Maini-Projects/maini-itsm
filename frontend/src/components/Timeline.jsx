import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, Loading, useFetch } from './ui'

const TYPES = [['incidents', 'Incidents'], ['problems', 'Problems'], ['defects', 'Defects'], ['changes', 'Changes'], ['releases', 'Releases']]
const PERIODS = [[7, 'Last 7 days'], [30, 'Last 30 days'], [90, 'Last 90 days'], [180, 'Last 6 months'], [365, 'Last 12 months']]
const BUCKETS = [['day', 'Daily'], ['week', 'Weekly'], ['month', 'Monthly']]
const LEVEL = {
  incidents: ['Priority', [['P1', 'Critical'], ['P2', 'High'], ['P3', 'Medium'], ['P4', 'Low']]],
  problems: ['Priority', [['P1', 'Critical'], ['P2', 'High'], ['P3', 'Medium'], ['P4', 'Low']]],
  defects: ['Severity', [['Critical', 'Critical'], ['High', 'High'], ['Medium', 'Medium'], ['Low', 'Low']]],
  changes: ['Risk', [['High', 'High'], ['Medium', 'Medium'], ['Low', 'Low']]],
  releases: ['Environment', [['Production', 'Production'], ['UAT', 'UAT']]],
}
const STATUSES = {
  incidents: ['New', 'Assigned', 'In Progress', 'Pending', 'Resolved', 'Closed'],
  problems: ['Identified', 'Investigating', 'Root Cause Identified', 'Fix Planned', 'Resolved', 'Closed'],
  defects: ['New', 'Assigned', 'In Progress', 'Pending', 'Resolved', 'Closed'],
  changes: ['Draft', 'Submitted', 'Under Review', 'Approval Pending', 'Scheduled', 'Implementation', 'Implemented', 'Closed'],
  releases: ['Planned', 'Under Review', 'Approved', 'Ready to Deploy', 'Deployment', 'Validated', 'Closed'],
}
const COLORS = {
  Critical: '#c0392b', High: '#e67e22', Medium: '#f1c40f', Low: '#2e9e6b', Production: '#c74634', UAT: '#2f8aa0',
  New: '#4a7fb5', Assigned: '#7a5aa6', 'In Progress': '#e67e22', Pending: '#f1c40f', Resolved: '#2e9e6b', Closed: '#7f8c8d',
}
const PALETTE = ['#c74634', '#2f8aa0', '#e0a03a', '#4a7fb5', '#2e9e6b', '#7a5aa6', '#d96a8a', '#6b8e23', '#b5651d', '#3d5a80']
const LINE = '#3d1a12'

const dateLabel = (iso, bucket) => {
  const d = new Date(`${iso}T00:00:00`)
  return bucket === 'month' ? d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' }) : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function Chart({ data }) {
  const [hover, setHover] = useState(null)
  const n = data.labels.length
  const W = 960, H = 300, L = 44, R = 16, T = 18, B = 34
  const pw = W - L - R, ph = H - T - B
  const top = Math.max(1, ...data.categories.flatMap((c) => data.created[c]), ...data.finished)
  const step = top <= 5 ? 1 : top <= 10 ? 2 : Math.ceil(top / 5 / 5) * 5
  const max = Math.ceil(top / step) * step
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step)
  const band = pw / n
  const x = (i) => L + band * i + band / 2
  const y = (v) => T + ph - (ph * v) / max
  const color = (c, i) => COLORS[c] || PALETTE[i % PALETTE.length]
  const every = Math.max(1, Math.ceil(n / 12))
  const line = data.finished.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join(' ')
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img" aria-label="Records over time">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#ece3de" />
            <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="#8a7f78">{t}</text>
          </g>
        ))}
        {data.labels.map((iso, i) => {
          let acc = 0
          return (
            <g key={iso} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={L + band * i} y={T} width={band} height={ph} fill={hover === i ? '#f8ece7' : 'transparent'} />
              {i % every === 0 && <text x={x(i)} y={H - 12} textAnchor="middle" fontSize="11" fill="#6f6862">{dateLabel(iso, data.bucket)}</text>}
            </g>
          )
        })}
        {data.categories.map((c, ci) => {
          const path = data.created[c].map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join(' ')
          return (
            <g key={c} pointerEvents="none">
              <path d={path} fill="none" stroke={color(c, ci)} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
              {data.created[c].map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={n > 40 ? 1.8 : 3.5} fill="#fff" stroke={color(c, ci)} strokeWidth="2" />)}
            </g>
          )
        })}
        <path d={line} fill="none" stroke={LINE} strokeWidth="2.5" strokeDasharray="6 4" strokeLinejoin="round" pointerEvents="none" />
        {data.finished.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={n > 40 ? 1.8 : 3.5} fill={LINE} pointerEvents="none" />)}
      </svg>
      <div className="tl-tip" aria-live="polite">
        {hover === null ? 'Hover the graph to see the numbers for that day, week or month.' : (
          <>
            <b>{dateLabel(data.labels[hover], data.bucket)}</b>
            {data.categories.map((c, ci) => data.created[c][hover] ? <span key={c}><i style={{ background: color(c, ci) }} />{c}: {data.created[c][hover]}</span> : null)}
            <span><i className="ln" />Finished: {data.finished[hover]}</span>
          </>
        )}
      </div>
      <div className="tl-legend">
        {data.categories.map((c, ci) => <span key={c}><i style={{ background: color(c, ci) }} />{c}</span>)}
        <span><i className="ln" />Finished (resolved or closed)</span>
      </div>
    </div>
  )
}

export default function Timeline() {
  const { me } = useAuth()
  const [f, setF] = useState({ type: 'incidents', days: 30, bucket: 'day', split: 'level', level: '', status: '', team_id: '', project_id: '' })
  const set = (k) => (e) => setF((o) => ({ ...o, [k]: e.target.value, ...(k === 'type' ? { level: '', status: '' } : {}) }))
  const teams = useFetch(() => (me.role === 'admin' ? api.get('/teams') : []), [me.role])
  const { data, error, loading } = useFetch(
    () => api.get('/reports/timeline', { ...f, level: f.level || undefined, status: f.status || undefined, team_id: f.team_id || undefined, project_id: f.project_id || undefined }),
    [JSON.stringify(f), (me.active_project_ids || []).join()],
  )
  const [levelName, levels] = LEVEL[f.type]
  const multiProject = (me.projects || []).length > 1
  return (
    <div className="card" style={{ marginBottom: 22 }}>
      <div className="head"><h3>Records over time</h3>
        {data && <span style={{ color: 'var(--muted)', fontSize: 12 }}>
          {data.created_total} created · {data.finished_total} finished
        </span>}
      </div>
      <div className="tl-filters">
        <select value={f.type} onChange={set('type')} aria-label="Record type">{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={f.days} onChange={set('days')} aria-label="Period">{PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={f.bucket} onChange={set('bucket')} aria-label="Group by">{BUCKETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={f.split} onChange={set('split')} aria-label="Split by">
          <option value="level">Split by {levelName.toLowerCase()}</option><option value="status">Split by status</option>
          {me.role === 'admin' && <option value="team">Split by team</option>}
          {multiProject && <option value="project">Split by project</option>}
          <option value="none">No split</option>
        </select>
        <select value={f.level} onChange={set('level')} aria-label={levelName}><option value="">{levelName}</option>{levels.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={f.status} onChange={set('status')} aria-label="Status"><option value="">Status</option>{STATUSES[f.type].map((s) => <option key={s}>{s}</option>)}</select>
        {me.role === 'admin' && <select value={f.team_id} onChange={set('team_id')} aria-label="Team"><option value="">Team</option>{(teams.data || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>}
        {multiProject && <select value={f.project_id} onChange={set('project_id')} aria-label="Project"><option value="">Project</option>{me.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>}
      </div>
      <ErrorBox error={error} />
      <div style={{ padding: '4px 16px 16px' }}>
        {loading && !data ? <Loading variant="bars" /> : data && (data.created_total || data.finished_total ? <Chart data={data} /> : <div className="empty">Nothing matches these filters in this period.</div>)}
      </div>
    </div>
  )
}

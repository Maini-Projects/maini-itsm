import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import Timeline from '../components/Timeline'
import { Empty, ErrorBox, Loading, fmtDate, priorityLabel, useAction, useFetch } from '../components/ui'

const DATE_KEY = /(_at|_start|_end)$/

// Meaningful colours for well-known labels; everything else cycles through the palette.
const SEMANTIC = {
  Critical: '#c0392b', High: '#e67e22', Medium: '#f1c40f', Low: '#2e9e6b',
  P1: '#c0392b', P2: '#e67e22', P3: '#f1c40f', P4: '#2e9e6b',
  New: '#4a7fb5', Assigned: '#7a5aa6', 'In Progress': '#e67e22', Pending: '#f1c40f', Resolved: '#2e9e6b', Closed: '#7f8c8d',
  Production: '#c74634', UAT: '#2f8aa0',
}
const PALETTE = ['#c74634', '#2f8aa0', '#e0a03a', '#4a7fb5', '#2e9e6b', '#7a5aa6', '#d96a8a', '#6b8e23', '#b5651d', '#3d5a80']
const colorFor = (label, i) => SEMANTIC[label] || PALETTE[i % PALETTE.length]

function BarChart({ chart, selected, onSelect }) {
  const values = chart.values.map((v) => Number(v) || 0)
  const total = values.reduce((a, b) => a + b, 0)
  const top = Math.max(1, ...values)
  const step = top <= 5 ? 1 : top <= 10 ? 2 : Math.ceil(top / 5 / 5) * 5
  const max = Math.ceil(top / step) * step
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step)
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div className="head"><h3>{chart.label}</h3><span style={{ color: 'var(--muted)', fontSize: 12 }}>Total: {total}</span></div>
      <div className="bchart">
        <div className="yaxis">{[...ticks].reverse().map((t) => <span key={t}>{t}</span>)}</div>
        <div className="plot" style={{ '--rows': ticks.length - 1 }}>
          {chart.labels.map((l, i) => {
            const v = values[i] ?? 0
            const c = colorFor(String(l), i)
            return (
              <div className={`bcol ${chart.links?.[i] ? 'link' : ''} ${selected === i ? 'on' : ''} ${selected !== null && selected !== i ? 'dim' : ''}`} key={i}
                onClick={() => chart.links?.[i] && onSelect(selected === i ? null : i)}
                title={`${l}: ${v}${total ? ` (${Math.round((100 * v) / total)}%)` : ''}${chart.links?.[i] ? ' · click to list these below' : ''}`}>
                <em>{v}</em>
                <i style={{ height: `${(100 * v) / max}%`, background: `linear-gradient(180deg, ${c}, ${c}cc)`, boxShadow: `0 4px 10px ${c}55`, animationDelay: `${i * 60}ms` }} />
              </div>
            )
          })}
        </div>
      </div>
      <div className="bchart-x">
        <span className="spacer" />
        <div>{chart.labels.map((l, i) => <label key={i} title={String(l)}><b style={{ background: colorFor(String(l), i) }} />{String(l)}</label>)}</div>
      </div>
    </div>
  )
}

export function Reports() {
  return (
    <>
      <div className="eyebrow">Reporting & Dashboards</div>
      <h2 className="title">Reports</h2>
      <Timeline />
    </>
  )
}


function BarRecords({ chart, index, onClear }) {
  const [path, query] = chart.links[index].split('?')
  const params = Object.fromEntries(new URLSearchParams(query || ''))
  const { data, error, loading } = useFetch(() => api.get(path, { ...params, limit: 100 }), [chart.links[index]])
  const rows = data?.items || []
  const title = (r) => r.short_description || r.title || r.name
  const extra = [['priority', 'Priority'], ['severity', 'Severity'], ['type', 'Type'], ['risk', 'Risk'], ['environment', 'Environment'], ['team_name', 'Team'], ['assignee_name', 'Assignee'], ['owner_name', 'Owner']]
    .filter(([k]) => rows.some((r) => r[k]))
  return (
    <div className="card table" style={{ marginBottom: 14 }}>
      <div className="head">
        <h3>{String(chart.labels[index])} · {data ? data.total : '…'} record{data?.total === 1 ? '' : 's'}</h3>
        <button className="btn2" onClick={onClear}>Clear selection ✕</button>
      </div>
      <ErrorBox error={error} />
      {loading && !data && <Loading variant="bars" />}
      {data && !rows.length && <Empty>Nothing matches this bar.</Empty>}
      {rows.length > 0 && (
        <table>
          <thead><tr><th>Number</th><th>Title</th>{extra.map(([, l]) => <th key={l}>{l}</th>)}<th>Status</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td><Link className="link" to={`${path}/${r.id}`}>{r.number}</Link></td><td>{title(r)}</td>
                {extra.map(([k]) => <td key={k}>{k === 'priority' ? priorityLabel(r[k]) : r[k] || '—'}</td>)}<td>{r.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.total > rows.length && <div className="empty">Showing the first {rows.length} of {data.total}. <Link className="link" to={chart.links[index]}>Open the full list</Link></div>}
    </div>
  )
}

export function ReportView() {
  const { key } = useParams()
  const { data: r, error, loading } = useFetch(() => api.get(`/reports/${key}`), [key])
  const [run, busy] = useAction()
  const [picked, setPicked] = useState(null)
  useEffect(() => setPicked(null), [key])
  const fmt = (col, v) => (v === null || v === undefined || v === '' ? '—' : DATE_KEY.test(col) ? fmtDate(v) : String(v))
  return (
    <>
      <Link to="/reports" className="back" style={{ display: 'inline-block' }}>‹ Back to reports</Link>
      <ErrorBox error={error} />
      {loading && <Loading variant="bars" />}
      {r && (
        <>
          <div className="eyebrow">{r.category}</div>
          <h2 className="title">{r.title}</h2>
          <p className="sub">Scope: {r.scope} · generated {fmtDate(r.generated_at)}</p>
          <div className="toolbar"><span />
            <div>
              <button className="btn2" disabled={busy} onClick={() => run(() => api.download(`/reports/${key}`, { format: 'csv' }, `${key}.csv`))}>Download CSV</button>{' '}
              <button className="btn2" disabled={busy} onClick={() => run(() => api.download(`/reports/${key}`, { format: 'pdf' }, `${key}.pdf`))}>Download PDF</button>
            </div>
          </div>
          {r.chart && r.chart.labels.length > 0 && <BarChart chart={r.chart} selected={picked} onSelect={setPicked} />}
          {r.chart && picked !== null && r.chart.links?.[picked] && <BarRecords chart={r.chart} index={picked} onClear={() => setPicked(null)} />}
          {!(picked !== null && r.chart?.links?.[picked]) && <div className="card table">
            {r.rows.length ? (
              <table>
                <thead><tr>{r.columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
                <tbody>{r.rows.map((row, i) => <tr key={i}>{r.columns.map((c) => <td key={c.key}>{fmt(c.key, row[c.key])}</td>)}</tr>)}</tbody>
              </table>
            ) : <Empty>No data for this report yet.</Empty>}
          </div>}
        </>
      )}
    </>
  )
}

import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Empty, ErrorBox, Loading, fmtDate, useAction, useFetch } from '../components/ui'

const DATE_KEY = /(_at|_start|_end)$/

export function Reports() {
  const navigate = useNavigate()
  const { data, error, loading } = useFetch(() => api.get('/reports'))
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('')
  const items = (data || []).filter((r) => (!cat || r.category === cat) && r.title.toLowerCase().includes(q.toLowerCase()))
  const cats = [...new Set((data || []).map((r) => r.category))]
  return (
    <>
      <div className="eyebrow">Reporting & Dashboards</div>
      <h2 className="title">Standard Reports</h2>
      <p className="sub">Live operational reports. Open a report to see the numbers, then download it as a CSV file (opens in Excel).</p>
      <div className="toolbar">
        <div className="filters">
          <input placeholder="Search reports" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search reports" />
          <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category"><option value="">All categories</option>{cats.map((c) => <option key={c}>{c}</option>)}</select>
        </div>
      </div>
      <ErrorBox error={error} />
      {loading && <Loading />}
      <div className="reports">
        {items.map((r) => (
          <button key={r.key} className={`report ${r.available ? '' : 'off'}`} onClick={() => r.available && navigate(`/reports/${r.key}`)} aria-disabled={!r.available}>
            <b>{r.title}</b><span>{r.category}</span>{!r.available && <span>Not available yet: {r.reason}</span>}
          </button>
        ))}
      </div>
      {data && !items.length && <Empty>No reports match.</Empty>}
    </>
  )
}

export function ReportView() {
  const { key } = useParams()
  const { data: r, error, loading } = useFetch(() => api.get(`/reports/${key}`), [key])
  const [run, busy] = useAction()
  const max = r?.chart ? Math.max(1, ...r.chart.values.map(Number)) : 1
  const fmt = (col, v) => (v === null || v === undefined || v === '' ? '—' : DATE_KEY.test(col) ? fmtDate(v) : String(v))
  return (
    <>
      <Link to="/reports" className="back" style={{ display: 'inline-block' }}>‹ Back to reports</Link>
      <ErrorBox error={error} />
      {loading && <Loading />}
      {r && (
        <>
          <div className="eyebrow">{r.category}</div>
          <h2 className="title">{r.title}</h2>
          <p className="sub">Scope: {r.scope} · generated {fmtDate(r.generated_at)}</p>
          <div className="toolbar"><span /><button className="btn2" disabled={busy} onClick={() => run(() => api.download(`/reports/${key}`, { format: 'csv' }, `${key}.csv`))}>Download CSV</button></div>
          {r.chart && r.chart.labels.length > 0 && (
            <div className="card" style={{ marginBottom: 14 }}>
              <div className="head"><h3>{r.chart.label}</h3></div>
              <div className="chart">
                {r.chart.labels.map((l, i) => (
                  <div className="bar" key={i}><em>{r.chart.values[i] ?? 0}</em><i style={{ height: `${(100 * Number(r.chart.values[i] || 0)) / max}%` }} /><label title={String(l)}>{String(l)}</label></div>
                ))}
              </div>
            </div>
          )}
          <div className="card table">
            {r.rows.length ? (
              <table>
                <thead><tr>{r.columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
                <tbody>{r.rows.map((row, i) => <tr key={i}>{r.columns.map((c) => <td key={c.key}>{fmt(c.key, row[c.key])}</td>)}</tr>)}</tbody>
              </table>
            ) : <Empty>No data for this report yet.</Empty>}
          </div>
        </>
      )}
    </>
  )
}

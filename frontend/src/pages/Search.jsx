import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useCustomers } from '../components/Customer'
import { Empty, ErrorBox, Loading, priorityLabel, useFetch } from '../components/ui'

const LABEL = { incidents: 'Incidents', problems: 'Problems', defects: 'Defects', changes: 'Changes', releases: 'Releases', customers: 'Customers', applications: 'Applications', users: 'Users' }
const RECORD = ['incidents', 'problems', 'defects', 'changes', 'releases']
const OTHER_LINK = { customers: '/projects', applications: '/services', users: '/admin' }

export default function Search() {
  const [sp] = useSearchParams()
  const q = (sp.get('q') || '').trim()
  const cust = useCustomers()
  const { data, error, loading } = useFetch(() => (q ? api.get('/search', { q }) : null), [q])
  const groups = (data?.groups || []).filter((g) => g.items.length)
  const total = groups.reduce((n, g) => n + g.total, 0)
  return (
    <>
      <div className="eyebrow">Search</div>
      <h2 className="title">Results for “{q}”</h2>
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && !groups.length && <div className="card"><Empty>Nothing matches “{q}”. Try fewer or different words.</Empty></div>}
      {data && groups.length > 0 && <p className="sub">{total} result{total === 1 ? '' : 's'}</p>}
      {groups.map((g) => (
        <div className="card table" key={g.kind} style={{ marginBottom: 14 }}>
          <div className="head"><h3>{LABEL[g.kind]}</h3><span style={{ color: 'var(--muted)', fontSize: 12 }}>{g.total} found</span></div>
          <table>
            {RECORD.includes(g.kind) ? (
              <>
                <thead><tr><th>Number</th>{cust.multi && <th>Project</th>}<th>Title</th><th>Level</th><th>Team</th><th>Status</th></tr></thead>
                <tbody>
                  {g.items.map((r) => (
                    <tr key={r.id}>
                      <td><Link className="link" to={`/${g.kind}/${r.id}`}>{r.number}</Link></td>
                      {cust.multi && <td>{cust.of(r)}</td>}
                      <td><b>{r.title}</b></td><td>{g.kind === 'incidents' || g.kind === 'problems' ? priorityLabel(r.level) : r.level}</td>
                      <td>{r.team_name || '—'}</td><td>{r.status}</td>
                    </tr>
                  ))}
                </tbody>
              </>
            ) : (
              <>
                <thead><tr><th>Name</th><th>Details</th></tr></thead>
                <tbody>
                  {g.items.map((r) => <tr key={r.id}><td><Link className="link" to={OTHER_LINK[g.kind]}>{r.title}</Link></td><td>{r.detail || '—'}</td></tr>)}
                </tbody>
              </>
            )}
          </table>
          {g.total > g.items.length && <div className="empty">Showing the first {g.items.length} of {g.total}.</div>}
        </div>
      ))}
    </>
  )
}

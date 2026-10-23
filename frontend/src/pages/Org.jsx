import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, Empty, ErrorBox, Loading, roleLabel, useFetch } from '../components/ui'

function Node({ person, kids, depth }) {
  return (
    <li>
      <div className="org-card" style={{ borderLeftColor: person.role === 'admin' ? '#7c251a' : person.role === 'manager' ? '#e0a03a' : '#c74634' }}>
        <b>{person.full_name}</b>
        <span>{person.email}</span>
        <span><Badge tone={person.role === 'admin' ? 'red' : person.role === 'manager' ? 'amber' : 'gray'}>{roleLabel(person.role)}</Badge>{person.team_name ? ` · ${person.team_name}` : ''}</span>
        {kids(person.id).length > 0 && <small>{kids(person.id).length} direct report{kids(person.id).length === 1 ? '' : 's'}</small>}
      </div>
      {kids(person.id).length > 0 && (
        <ul>{kids(person.id).map((k) => <Node key={k.id} person={k} kids={kids} depth={depth + 1} />)}</ul>
      )}
    </li>
  )
}

export default function Org() {
  const { me } = useAuth()
  const internal = (me.projects || []).filter((p) => p.is_internal)
  const [pid, setPid] = useState(internal[0]?.id || '')
  const { data, error, loading } = useFetch(() => (pid ? api.get(`/org/${pid}`) : null), [pid])
  const people = data?.people || []
  const ids = new Set(people.map((p) => p.id))
  const kids = (id) => people.filter((p) => p.reports_to === id)
  const roots = people.filter((p) => !p.reports_to || !ids.has(p.reports_to))
  return (
    <>
      <div className="eyebrow">Administration</div>
      <h2 className="title">Org chart</h2>
      {internal.length > 1 && (
        <div className="toolbar"><div className="filters">
          <select value={pid} onChange={(e) => setPid(e.target.value)} aria-label="Organization">{internal.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        </div></div>
      )}
      <ErrorBox error={error} />
      {!internal.length && <div className="card"><Empty>No internal organizations yet. Mark a customer as internal on the Customers page to use reporting lines.</Empty></div>}
      {loading && !data && <Loading />}
      {data && !people.length && <div className="card"><Empty>No one is assigned to this organization yet.</Empty></div>}
      {data && people.length > 0 && (
        <div className="card" style={{ padding: 18, overflowX: 'auto' }}>
          <ul className="orgtree">{roots.map((r) => <Node key={r.id} person={r} kids={kids} depth={0} />)}</ul>
        </div>
      )}
    </>
  )
}

import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, Empty, ErrorBox, Field, FormModal, Loading, fmtShort, roleLabel, useFetch, useToast } from '../components/ui'

export default function Projects() {
  const { me } = useAuth()
  const { data, error, loading, reload } = useFetch(() => api.get('/projects/overview'))
  const [modal, setModal] = useState(null) // { kind: 'new' } | { kind: 'people', project }
  const admin = me.role === 'admin'
  return (
    <>
      <div className="eyebrow">Administration</div>
      <h2 className="title">Projects</h2>
      <p className="sub">
        {admin ? 'Add projects and choose who works on each one.' : "Choose which of your team's customers can see each of your projects."}
      </p>
      <div className="toolbar">
        <span />
        {admin && <button className="btn" onClick={() => setModal({ kind: 'new' })}>+ New Project</button>}
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Project</th><th>Support engineers</th><th>Customers</th><th>Created</th><th /></tr></thead>
          <tbody>
            {data?.map((p) => (
              <tr key={p.id}>
                <td><b>{p.name}</b></td><td>{p.support_engineers}</td><td>{p.customers}</td><td>{fmtShort(p.created_at)}</td>
                <td><button className="btn2" onClick={() => setModal({ kind: 'people', project: p })}>{admin ? 'Assign people' : 'Assign customers'}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.length && <Empty>No projects yet.</Empty>}
      </div>
      {modal?.kind === 'new' && <NewProject onClose={() => setModal(null)} onSaved={reload} />}
      {modal?.kind === 'people' && <People project={modal.project} onClose={() => setModal(null)} onSaved={reload} />}
    </>
  )
}

function NewProject({ onClose, onSaved }) {
  const toast = useToast()
  const [name, setName] = useState('')
  return (
    <FormModal title="New project" submitLabel="Create project" onClose={onClose} width={460}
      onSubmit={async () => { await api.post('/projects', { name }); toast('Project created.'); onSaved() }}>
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label="Project name"><input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></Field>
      </div>
    </FormModal>
  )
}

const box = { width: 16, height: 16, margin: 0, flex: 'none', accentColor: 'var(--brand)' }

function People({ project, onClose, onSaved }) {
  const toast = useToast()
  const { data, error } = useFetch(() => api.get(`/projects/${project.id}/members`))
  const [picked, setPicked] = useState(null)
  const ids = picked ?? (data || []).filter((u) => u.member).map((u) => u.id)
  const toggle = (id) => setPicked(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id])
  return (
    <FormModal title={`People on ${project.name}`} submitLabel="Save" onClose={onClose} width={560}
      onSubmit={async () => { await api.put(`/projects/${project.id}/members`, { user_ids: ids }); toast('Project people saved.'); onSaved() }}>
      <div style={{ padding: 15 }}>
        <ErrorBox error={error} />
        {!data && !error && <Loading />}
        {data && !data.length && <Empty>No one to assign.</Empty>}
        {data?.map((u) => (
          <label key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', fontSize: 13, textTransform: 'none', letterSpacing: 0, fontWeight: 500, color: 'var(--text)' }}>
            <input type="checkbox" style={box} checked={ids.includes(u.id)} onChange={() => toggle(u.id)} />
            <span><b>{u.full_name}</b> <span style={{ color: 'var(--muted)' }}>{u.email}</span></span>
            <Badge tone={u.role === 'manager' ? 'blue' : 'gray'}>{roleLabel(u.role)}</Badge>
          </label>
        ))}
      </div>
    </FormModal>
  )
}

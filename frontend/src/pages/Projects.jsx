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
      <h2 className="title">Customers</h2>
      <div className="toolbar">
        <span />
        {admin && <button className="btn" onClick={() => setModal({ kind: 'new' })}>+ New Customer</button>}
      </div>
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Customer</th><th>Project name</th><th>Type</th><th>Support engineers</th><th>Customer users</th><th>Created</th><th /></tr></thead>
          <tbody>
            {data?.map((p) => (
              <tr key={p.id}>
                <td><b>{p.name}</b></td><td>{p.project_name || '—'}</td><td>{p.is_internal ? 'Internal' : 'External'}</td><td>{p.support_engineers}</td><td>{p.customers}</td><td>{fmtShort(p.created_at)}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="btn2" onClick={() => setModal({ kind: 'people', project: p })}>{admin ? 'Assign people' : 'Assign customer users'}</button>
                  {admin && <>{' '}<button className="btn2" onClick={() => setModal({ kind: 'rename', project: p })}>Edit</button></>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.length && <Empty>No customers yet.</Empty>}
      </div>
      {modal?.kind === 'new' && <NewProject onClose={() => setModal(null)} onSaved={reload} />}
      {modal?.kind === 'rename' && <RenameProject project={modal.project} onClose={() => setModal(null)} onSaved={reload} />}
      {modal?.kind === 'people' && <People project={modal.project} onClose={() => setModal(null)} onSaved={reload} />}
    </>
  )
}

function NewProject({ onClose, onSaved }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [projectName, setProjectName] = useState('')
  const [internal, setInternal] = useState(false)
  return (
    <FormModal title="New customer" submitLabel="Create customer" onClose={onClose} width={460}
      onSubmit={async () => { await api.post('/projects', { name, project_name: projectName || null, is_internal: internal }); toast('Customer created.'); onSaved() }}>
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label="Customer name"><input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></Field>
        <Field label="Project name (optional)"><input value={projectName} onChange={(e) => setProjectName(e.target.value)} /></Field>
        <Field label="Type"><select value={internal ? 'internal' : 'external'} onChange={(e) => setInternal(e.target.value === 'internal')}><option value="external">External client</option><option value="internal">Internal organization</option></select></Field>
      </div>
    </FormModal>
  )
}

function RenameProject({ project, onClose, onSaved }) {
  const toast = useToast()
  const [name, setName] = useState(project.name)
  const [projectName, setProjectName] = useState(project.project_name || '')
  const [internal, setInternal] = useState(!!project.is_internal)
  return (
    <FormModal title={`Edit ${project.name}`} submitLabel="Save" onClose={onClose} width={460}
      onSubmit={async () => { await api.patch(`/projects/${project.id}`, { name, project_name: projectName || null, is_internal: internal }); toast('Customer saved.'); onSaved() }}>
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label="Customer name"><input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></Field>
        <Field label="Project name"><input value={projectName} onChange={(e) => setProjectName(e.target.value)} /></Field>
        <Field label="Type"><select value={internal ? 'internal' : 'external'} onChange={(e) => setInternal(e.target.value === 'internal')}><option value="external">External client</option><option value="internal">Internal organization</option></select></Field>
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

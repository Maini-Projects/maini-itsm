import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ProjectFilter, useCustomers } from '../components/Customer'
import { Badge, Empty, ErrorBox, Field, FormModal, Loading, fmtShort, useDebounced, useFetch, useToast } from '../components/ui'

function Editor({ article, categories, onClose, onSaved }) {
  const { me } = useAuth()
  const cust = useCustomers()
  const toast = useToast()
  const [f, setF] = useState({
    title: article?.title || '', body: article?.body || '', category: article?.category || '',
    audience: article?.audience || 'everyone', status: article?.status || 'draft', customer: me.active_project_ids?.[0] || '',
  })
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async () => {
    const body = { title: f.title, body: f.body, category: f.category || null, audience: f.audience, status: f.status }
    const saved = article
      ? await api.patch(`/kb/${article.id}`, body)
      : await api.post(cust.multi ? `/kb?customer=${f.customer}` : '/kb', body)
    toast(article ? 'Article saved.' : 'Article created.')
    onSaved(saved)
  }
  return (
    <FormModal title={article ? 'Edit article' : 'New article'} submitLabel="Save" onClose={onClose} onSubmit={submit} width={680}>
      <div className="form">
        <Field label="Title" wide><input value={f.title} onChange={set('title')} required minLength={3} autoFocus /></Field>
        <Field label="Category">
          <input value={f.category} onChange={set('category')} list="kb-cats" />
          <datalist id="kb-cats">{categories.map((c) => <option key={c} value={c} />)}</datalist>
        </Field>
        <Field label="Who can read it">
          <select value={f.audience} onChange={set('audience')}><option value="everyone">Everyone</option><option value="staff">Staff only</option></select>
        </Field>
        <Field label="Status">
          <select value={f.status} onChange={set('status')}><option value="draft">Draft</option><option value="published">Published</option></select>
        </Field>
        {!article && cust.multi && (
          <Field label="Customer">
            <select value={f.customer} onChange={set('customer')}>{cust.projects.filter((p) => me.active_project_ids.includes(p.id)).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
          </Field>
        )}
        <Field label="Article" wide><textarea rows={12} value={f.body} onChange={set('body')} /></Field>
      </div>
    </FormModal>
  )
}

export function KnowledgeList() {
  const { me } = useAuth()
  const cust = useCustomers()
  const staff = me.role !== 'employee'
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [projectId, setProjectId] = useState('')
  const [editing, setEditing] = useState(false)
  const dq = useDebounced(q)
  const navigate = useNavigate()
  const { data, error, loading, reload } = useFetch(
    () => api.get('/kb', { q: dq.trim() || undefined, category: category || undefined, project_id: projectId || undefined }),
    [dq, category, projectId],
  )
  return (
    <>
      <div className="eyebrow">Self service</div>
      <h2 className="title">Knowledge base</h2>
      <div className="toolbar">
        <div className="filters">
          <ProjectFilter cust={cust} value={projectId} onChange={setProjectId} />
          <input placeholder="Search articles" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search articles" />
          <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
            <option value="">Category</option>{(data?.categories || []).map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        {staff && <button className="btn" onClick={() => setEditing(true)}>+ New Article</button>}
      </div>
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && !data.items.length && (
        <div className="card"><div className="kb-empty"><b>No articles yet</b><span>{staff ? 'Create the first one with “+ New Article”.' : 'Guides and answers to common questions will appear here.'}</span></div></div>
      )}
      <div className="kb-grid">
        {data?.items.map((a) => (
          <Link key={a.id} to={`/kb/${a.id}`} className="kb-card">
            <div className="kb-meta">
              {a.category && <Badge tone="blue">{a.category}</Badge>}
              {staff && a.status === 'draft' && <Badge tone="amber">Draft</Badge>}
              {staff && a.audience === 'staff' && <Badge tone="gray">Staff only</Badge>}
              {cust.multi && <Badge tone="gray">{cust.of(a)}</Badge>}
            </div>
            <b>{a.title}</b>
            <p>{a.body}{a.body.length >= 220 ? '…' : ''}</p>
            <small>Updated {fmtShort(a.updated_at)} · {a.created_by_name}</small>
          </Link>
        ))}
      </div>
      {editing && <Editor categories={data?.categories || []} onClose={() => setEditing(false)} onSaved={(a) => navigate(`/kb/${a.id}`)} />}
    </>
  )
}

export function KnowledgeArticle() {
  const { id } = useParams()
  const { me } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const staff = me.role !== 'employee'
  const [editing, setEditing] = useState(false)
  const { data: a, error, loading, reload } = useFetch(() => api.get(`/kb/${id}`), [id])
  const cats = useFetch(() => api.get('/kb', { limit: 1 }))
  const remove = async () => {
    if (!window.confirm('Delete this article? This cannot be undone.')) return
    await api.del(`/kb/${id}`)
    toast('Article deleted.')
    navigate('/kb')
  }
  return (
    <>
      <Link to="/kb" className="back" style={{ display: 'inline-block' }}>‹ Back to knowledge base</Link>
      <ErrorBox error={error} />
      {loading && !a && <Loading />}
      {a && (
        <article className="card kb-article">
          <div className="kb-meta">
            {a.category && <Badge tone="blue">{a.category}</Badge>}
            {staff && a.status === 'draft' && <Badge tone="amber">Draft</Badge>}
            {staff && a.audience === 'staff' && <Badge tone="gray">Staff only</Badge>}
          </div>
          <h2 className="title">{a.title}</h2>
          <small className="kb-by">Updated {fmtShort(a.updated_at)} · {a.created_by_name}</small>
          <div className="kb-body">{a.body || <Empty>This article is empty.</Empty>}</div>
          {staff && (
            <div className="kb-actions">
              <button className="btn" onClick={() => setEditing(true)}>Edit</button>{' '}
              <button className="danger" onClick={remove}>Delete</button>
            </div>
          )}
        </article>
      )}
      {editing && a && <Editor article={a} categories={cats.data?.categories || []} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); reload() }} />}
    </>
  )
}

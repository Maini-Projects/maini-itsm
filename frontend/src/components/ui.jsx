import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'

// ---- formatting ----------------------------------------------------------------------------
export function fmtDate(v) {
  if (!v) return '—'
  const d = new Date(v)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}
export function fmtShort(v) {
  if (!v) return '—'
  return new Date(v).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
export function toInputDate(v) { // value for <input type="datetime-local">
  if (!v) return ''
  const d = new Date(v)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
export const fromInputDate = (v) => (v ? new Date(v).toISOString() : null)

export function fmtMinutes(m) {
  if (m === null || m === undefined) return '—'
  const abs = Math.abs(m)
  const d = Math.floor(abs / 1440), h = Math.floor((abs % 1440) / 60), mi = abs % 60
  const text = d ? `${d}d ${h}h` : h ? `${h}h ${mi}m` : `${mi}m`
  return m < 0 ? `${text} overdue` : `${text} left`
}
export function fmtTarget(m) {
  if (m % 1440 === 0) return `${m / 1440}d`
  if (m % 60 === 0) return `${m / 60}h`
  return `${m}m`
}

// ---- role names ---------------------------------------------------------------------------
// Roles are stored as admin / manager / employee; these are the names people see.
export const ROLE_LABELS = { admin: 'Administrator', manager: 'Support Engineer', employee: 'Customer' }
export const roleLabel = (r) => ROLE_LABELS[r] || r

// ---- badges --------------------------------------------------------------------------------
const STATUS_TONE = {
  New: 'blue', Assigned: 'amber', 'In Progress': 'blue', Pending: 'gray', Resolved: 'green',
  Closed: 'gray', Identified: 'blue', Investigating: 'amber', 'Root Cause Identified': 'green', 'Fix Planned': 'blue',
  Draft: 'gray', Submitted: 'blue', 'Under Review': 'amber', 'Approval Pending': 'amber', Scheduled: 'blue',
  Implementation: 'amber', Implemented: 'green', Planned: 'gray', Approved: 'green', 'Ready to Deploy': 'green',
  Deployment: 'amber', Validated: 'green', pending: 'amber', approved: 'green', rejected: 'red', active: 'green',
  disabled: 'gray',
}
export const Badge = ({ tone, children }) => <span className={`badge ${tone || 'gray'}`}>{children}</span>
export const StatusBadge = ({ status }) => <Badge tone={STATUS_TONE[status]}>{status}</Badge>
export const SeverityBadge = ({ severity }) => <Badge tone={{ Critical: 'red', High: 'amber', Medium: 'blue', Low: 'gray' }[severity]}>{severity}</Badge>
export const RiskBadge = ({ risk }) => <Badge tone={{ High: 'red', Medium: 'amber', Low: 'green' }[risk]}>{risk}</Badge>
// Priority is stored as P1-P4 and shown as Critical / High / Medium / Low (listed here from lowest to highest).
export const PRIORITIES = [['P4', 'Low'], ['P3', 'Medium'], ['P2', 'High'], ['P1', 'Critical']]
export const priorityLabel = (p) => (PRIORITIES.find(([v]) => v === p) || [])[1] || p
export const Priority = ({ p }) => <span className={p === 'P1' ? 'p1' : p === 'P2' ? 'p2' : ''}>{priorityLabel(p)}</span>

// How long a ticket has been open: "1d 1h", "3h 20m", "12m". Finished tickets show how long they took.
export function fmtAge(ms) {
  const mins = Math.max(0, Math.floor(ms / 60000))
  const d = Math.floor(mins / 1440), h = Math.floor((mins % 1440) / 60), m = mins % 60
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return mins < 1 ? 'under 1m' : `${m}m`
}

export function OpenFor({ inc }) {
  const done = inc.status === 'Closed' || inc.status === 'Resolved'
  const end = done ? new Date(inc.resolved_at || inc.closed_at || Date.now()) : new Date()
  const age = fmtAge(end - new Date(inc.created_at))
  return <span title={`Raised ${fmtDate(inc.created_at)}`}>{done ? `Resolved in ${age}` : `Open for ${age}`}</span>
}

// The open tab of a detail page lives in the address (?tab=attachments), so a reload or a shared link opens the same tab.
export function useTab(valid, initial = 'details') {
  const [sp, setSp] = useSearchParams()
  const wanted = sp.get('tab')
  const tab = valid.includes(wanted) ? wanted : initial
  const setTab = (t) => {
    const next = new URLSearchParams(sp)
    if (t === initial) next.delete('tab'); else next.set('tab', t)
    setSp(next, { replace: true }) // no extra browser-history entry for every tab click
  }
  return [tab, setTab]
}

// ---- data loading --------------------------------------------------------------------------
export function useFetch(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const run = useCallback(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    Promise.resolve(fn()).then(
      (data) => live && setState({ data, error: null, loading: false }),
      (error) => live && setState({ data: null, error, loading: false }),
    )
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => run(), [run])
  return { ...state, reload: run }
}

export const Loading = ({ text = 'Loading…' }) => <div className="loading">{text}</div>
export const ErrorBox = ({ error }) => (error ? <div className="errorbox">{error.message || String(error)}</div> : null)
export const Empty = ({ children }) => <div className="empty">{children}</div>

export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}

// ---- toasts --------------------------------------------------------------------------------
const ToastCtx = createContext(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((text, kind = 'ok') => {
    const id = Math.random()
    setItems((x) => [...x, { id, text, kind }])
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 4500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((i) => <div key={i.id} className={`toast ${i.kind === 'err' ? 'err' : ''}`}>{i.text}</div>)}
      </div>
    </ToastCtx.Provider>
  )
}

// ---- modal ---------------------------------------------------------------------------------
export function Modal({ title, onClose, children, footer, width }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modalwrap" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} style={width ? { width } : undefined}>
        <div className="mhead"><h3>{title}</h3><button onClick={onClose} aria-label="Close">×</button></div>
        <div className="mbody">{children}</div>
        {footer && <div className="mfoot">{footer}</div>}
      </div>
    </div>
  )
}

// A modal with a form: runs `onSubmit`, shows the server's message on failure, closes on success.
export function FormModal({ title, submitLabel = 'Save', onClose, onSubmit, children, width, danger }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try { await onSubmit(); onClose() } catch (err) { setError(err.message); setBusy(false) }
  }
  return (
    <Modal title={title} onClose={onClose} width={width}>
      <form onSubmit={submit}>
        {children}
        {error && <div className="formerror">{error}</div>}
        <div className="mfoot">
          <button type="button" className="btn2" onClick={onClose}>Cancel</button>
          <button type="submit" className={danger ? 'danger' : 'btn'} disabled={busy}>{busy ? 'Working…' : submitLabel}</button>
        </div>
      </form>
    </Modal>
  )
}

// ---- form fields ---------------------------------------------------------------------------
export function Field({ label, wide, children }) {
  return (
    <div className={`field ${wide ? 'wide' : ''}`}>
      <label>{label}</label>
      {children}
    </div>
  )
}
export const Text = ({ value }) => <div className="ro">{value || '—'}</div>

// ---- pager ---------------------------------------------------------------------------------
export function Pager({ total, limit, offset, onChange }) {
  if (!total) return null
  const from = offset + 1, to = Math.min(offset + limit, total)
  return (
    <div className="pager">
      <span>Showing {from}–{to} of {total}</span>
      <div>
        <button className="btn2" disabled={offset <= 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
        <button className="btn2" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
      </div>
    </div>
  )
}

// ---- workflow bar and activity timeline ----------------------------------------------------
export function Workflow({ steps, current }) {
  const idx = steps.indexOf(current)
  return (
    <div className="workflow">
      {steps.map((s, i) => (
        <div key={s} className={`wf ${i < idx ? 'done' : i === idx ? 'current' : ''}`}>{s}</div>
      ))}
    </div>
  )
}

export const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`)

export function Timeline({ events, onChanged }) {
  const toast = useToast()
  const download = async (a) => {
    try { await api.download(`/attachments/${a.id}/download`, undefined, a.file_name) } catch (e) { toast(e.message, 'err') }
  }
  const remove = async (a) => {
    if (!window.confirm(`Remove “${a.file_name}”?`)) return
    try { await api.del(`/attachments/${a.id}`); toast('File removed.'); onChanged() } catch (e) { toast(e.message, 'err') }
  }
  if (!events) return <Loading />
  if (!events.length) return <Empty>No activity yet.</Empty>
  return (
    <>
      {events.map((e, i) => (
        <div key={i} className={`activity-entry ${e.type === 'note' ? 'note-entry' : ''} ${e.internal ? 'internal' : ''}`}>
          <span className="activity-dot" />
          <div className="activity-content">
            <b>
              {e.type === 'note' ? (e.internal ? 'Internal note' : 'Note') : e.text}{' '}
              <small>· {e.actor} · {fmtDate(e.at)}</small>
            </b>
            {e.type === 'note' && <p>{e.text}</p>}
            {e.type === 'attachment' && e.attachment && (
              <p style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span>{fmtSize(e.attachment.size_bytes)}</span>
                <button className="btn2" onClick={() => download(e.attachment)}>Download</button>
                {e.attachment.can_delete && onChanged && <button className="danger" onClick={() => remove(e.attachment)}>Remove</button>}
              </p>
            )}
          </div>
        </div>
      ))}
    </>
  )
}

// ---- pickers -------------------------------------------------------------------------------
// Pick a person (for assigning) from a list loaded by the caller. Type to search by name, email, team or role.
const personLabel = (p) => `${p.full_name}${p.team_name ? ` · ${p.team_name}` : ''} (${roleLabel(p.role)})`
export function PersonSelect({ people, value, onChange, placeholder = 'Choose a person' }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const box = useRef(null)
  const chosen = people.find((p) => p.id === value)
  useEffect(() => {
    const close = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const term = q.trim().toLowerCase()
  const shown = people.filter((p) => !term || `${p.full_name} ${p.email || ''} ${p.team_name || ''} ${roleLabel(p.role)}`.toLowerCase().includes(term))
  const pick = (p) => { onChange(p.id); setQ(''); setOpen(false) }
  const onKey = (e) => {
    if (e.key === 'Escape') setOpen(false)
    if (e.key === 'Enter') { e.preventDefault(); if (shown.length) pick(shown[0]) }
  }
  return (
    <div className="picker" ref={box}>
      <input
        value={open ? q : chosen ? personLabel(chosen) : ''} placeholder={`${placeholder} (type to search)`}
        onFocus={() => { setQ(''); setOpen(true) }} onClick={() => setOpen(true)}
        onChange={(e) => { setQ(e.target.value); setOpen(true) }} onKeyDown={onKey}
        aria-label={placeholder} autoComplete="off"
      />
      {open && (
        <div className="results">
          {shown.length ? shown.map((p) => (
            <button key={p.id} type="button" onClick={() => pick(p)}><b>{p.full_name}</b> · {p.email}<br /><small>{p.team_name || 'No team'} · {roleLabel(p.role)}</small></button>
          )) : <div style={{ padding: '9px 10px', fontSize: 12, color: 'var(--muted)' }}>{people.length ? 'No one matches that search.' : 'No people available to assign.'}</div>}
        </div>
      )}
    </div>
  )
}

// Search another record by number or text, then pick it. `path` is the list endpoint.
export function RecordPicker({ path, label, onPick, placeholder }) {
  const [q, setQ] = useState('')
  const dq = useDebounced(q, 250)
  const [results, setResults] = useState([])
  const box = useRef(null)
  useEffect(() => {
    let live = true
    if (dq.trim().length < 2) { setResults([]); return }
    api.get(path, { q: dq.trim(), limit: 6 }).then((r) => live && setResults(r.items || [])).catch(() => live && setResults([]))
    return () => { live = false }
  }, [dq, path])
  return (
    <div className="picker" ref={box}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      {results.length > 0 && (
        <div className="results">
          {results.map((r) => (
            <button key={r.id} type="button" onClick={() => { onPick(r); setQ(''); setResults([]) }}>
              <b>{r.number}</b> · {label(r)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ---- small hooks ---------------------------------------------------------------------------
// Runs an async action with a busy flag and a toast on success/failure.
export function useAction() {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const run = async (fn, okText) => {
    setBusy(true)
    try {
      const out = await fn()
      if (okText) toast(okText)
      return out
    } catch (e) {
      toast(e.message, 'err')
      return undefined
    } finally { setBusy(false) }
  }
  return [run, busy]
}

// ---- the title line and dropdown bar at the top of every record screen -------------------------
export function DetailTitle({ number, title, status }) {
  return (
    <div className="dtitle">
      <h2 className="dnum">{number}</h2><h2 className="dname">{title}</h2><StatusBadge status={status} />
    </div>
  )
}

// fields: [{ label, value, options: [{ value, label }], onChange(value) -> saves it, locked, disabled, title }]
// Edits are only held on screen; a Save button appears once something differs from what is stored.
export function FieldBar({ fields }) {
  const [draft, setDraft] = useState({})
  const [saving, setSaving] = useState(false)
  const dirty = fields.filter((f) => f.onChange && !f.locked && draft[f.label] !== undefined && draft[f.label] !== f.value)
  const save = async () => {
    setSaving(true)
    try {
      // the status goes last: moving on (for example to Resolved) may open a window of its own
      for (const f of [...dirty].sort((x, y) => (x.label === 'Status') - (y.label === 'Status'))) await f.onChange(draft[f.label])
    } finally { setSaving(false); setDraft({}) }
  }
  return (
    <div className="infobar">
      {fields.map((f) => (
        <div className="field" key={f.label}>
          <label>{f.label}</label>
          {f.text !== undefined || f.locked
            ? <div className="ro-box" title={f.title}>{(f.text !== undefined ? f.text : (f.options.find((o) => o.value === f.value) || {}).label) || '—'}</div>
            : (
              <select className={dirty.includes(f) ? 'changed' : ''} value={draft[f.label] ?? f.value ?? ''} disabled={f.disabled || saving} title={f.title}
                onChange={(e) => setDraft({ ...draft, [f.label]: e.target.value })}>
                {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            )}
        </div>
      ))}
      {dirty.length > 0 && (
        <div className="infobar-save">
          <span>You have unsaved changes</span>
          <button type="button" className="btn2" onClick={() => setDraft({})} disabled={saving}>Discard</button>
          <button type="button" className="btn" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
        </div>
      )}
    </div>
  )
}

// The Status dropdown: the current status plus every status the viewer may move it to.
export function statusField({ status, actions, busy, onPick, none, label = (s) => s }) {
  const next = [...new Map(actions.map((a) => [a.to, a])).values()]
  return {
    label: 'Status', value: status, locked: next.length === 0, disabled: busy, title: next.length === 0 ? none : undefined,
    options: [{ value: status, label: label(status) }, ...next.map((a) => ({ value: a.to, label: label(a.to) }))],
    onChange: (to) => { const a = next.find((x) => x.to === to); return a ? onPick(a) : undefined },
  }
}

// A filter value passed in the address, e.g. /incidents?priority=P1 (used when a report bar is clicked)
export const urlParam = (k) => new URLSearchParams(window.location.search).get(k) || ''

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
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
export function Field({ label, wide, hint, children }) {
  return (
    <div className={`field ${wide ? 'wide' : ''}`}>
      <label>{label}</label>
      {children}
      {hint && <div className="hint">{hint}</div>}
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

export function Timeline({ events }) {
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
          </div>
        </div>
      ))}
    </>
  )
}

// ---- pickers -------------------------------------------------------------------------------
// Pick a person (for assigning) from a list loaded by the caller. Type to search by name, email, team or role.
const personLabel = (p) => `${p.full_name}${p.team_name ? ` · ${p.team_name}` : ''} (${p.role})`
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
  const shown = people.filter((p) => !term || `${p.full_name} ${p.email || ''} ${p.team_name || ''} ${p.role}`.toLowerCase().includes(term))
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
            <button key={p.id} type="button" onClick={() => pick(p)}><b>{p.full_name}</b> · {p.email}<br /><small>{p.team_name || 'No team'} · {p.role}</small></button>
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

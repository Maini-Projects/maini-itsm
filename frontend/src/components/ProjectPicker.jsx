import { useEffect, useRef, useState } from 'react'

const box = { width: 16, height: 16, margin: 0, padding: 0, flex: 'none', accentColor: 'var(--brand)' }
const row = { display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', cursor: 'pointer', fontSize: 13, fontWeight: 500, textTransform: 'none', letterSpacing: 0, color: 'var(--text)' }

// A dropdown where one or several projects can be ticked, with a Select all option.
export default function ProjectPicker({ projects, picked, onChange, onClose, compact }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen((o) => { if (o && onClose) onClose(); return false }) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  })
  const all = projects.length > 0 && projects.every((p) => picked.includes(p.id))
  const toggle = (id) => onChange(picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id])
  const names = projects.filter((p) => picked.includes(p.id)).map((p) => p.name)
  const summary = !names.length ? 'Select projects…' : all && projects.length > 1 ? `All projects (${names.length})` : names.join(', ')
  return (
    <div ref={ref} style={{ position: 'relative', minWidth: compact ? 230 : undefined }}>
      <button type="button" onClick={() => setOpen((o) => { if (o && onClose) onClose(); return !o })} aria-haspopup="listbox" aria-expanded={open}
        style={{ width: '100%', height: 40, padding: '0 12px', border: '1px solid var(--line)', borderRadius: 8, background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, font: 'inherit', textAlign: 'left', color: names.length ? 'var(--text)' : 'var(--muted)' }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{summary}</span><span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div role="listbox" aria-multiselectable="true"
          style={{ position: 'absolute', zIndex: 40, left: 0, right: 0, top: 'calc(100% + 4px)', background: '#fff', border: '1px solid var(--line)', borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,.12)', maxHeight: 240, overflowY: 'auto' }}>
          <label style={{ ...row, borderBottom: '1px solid var(--line)', fontWeight: 700 }}>
            <input type="checkbox" style={box} checked={all} onChange={() => onChange(all ? [] : projects.map((p) => p.id))} /> Select all projects
          </label>
          {projects.map((p) => (
            <label key={p.id} style={row}>
              <input type="checkbox" style={box} checked={picked.includes(p.id)} onChange={() => toggle(p.id)} /> {p.name}
            </label>
          ))}
          {!projects.length && <div style={{ ...row, color: 'var(--muted)' }}>No projects yet</div>}
        </div>
      )}
    </div>
  )
}

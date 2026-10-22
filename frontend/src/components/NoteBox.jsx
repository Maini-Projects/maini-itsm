import { useRef, useState } from 'react'
import { api } from '../api'
import { fmtSize, useAction, useFetch, useToast } from './ui'

// The box at the top of an Activity tab. Incidents and defects get "Add a note" (with an optional file);
// problems, changes and releases have no notes, so they get "Attach a file" only.
// kind is the record's url name: incidents, problems, defects, changes or releases.
export default function NoteBox({ kind, id, staff, notes = true, ownerLabel = 'requester', onAdded }) {
  const toast = useToast()
  const info = useFetch(() => api.get(`/${kind}/${id}/attachments`), [kind, id]) // may this person attach? limits?
  const [body, setBody] = useState('')
  const [internal, setInternal] = useState(false)
  const [files, setFiles] = useState([])
  const [run, busy] = useAction()
  const input = useRef(null)
  const canAttach = !!info.data?.can_upload
  if (!notes && !canAttach) return null // nothing to offer: the timeline still lists the files

  const pick = (e) => {
    const picked = [...e.target.files]
    e.target.value = '' // so picking the same file again still works
    const ok = []
    picked.forEach((f) => {
      const ext = f.name.includes('.') ? f.name.split('.').pop().toLowerCase() : ''
      if (f.size > info.data.max_bytes) toast(`“${f.name}” is larger than 1 MB. Please choose a smaller file.`, 'err')
      else if (!info.data.allowed_extensions.includes(ext)) toast(`“${f.name}” is not an allowed file type.`, 'err')
      else ok.push(f)
    })
    setFiles((cur) => [...cur, ...ok])
  }

  const hasNote = notes && body.trim().length > 0
  const submit = () => run(async () => {
    if (hasNote) {
      await api.post(`/${kind}/${id}/comments`, { body, internal: staff && internal })
      setBody(''); setInternal(false)
    }
    const failed = []
    const problems = []
    for (const f of files) {
      try {
        const form = new FormData()
        form.append('file', f)
        await api.upload(`/${kind}/${id}/attachments`, form)
      } catch (e) { failed.push(f); problems.push(`${f.name}: ${e.message}`) }
    }
    setFiles(failed) // a file that did not go through stays in the box so it can be tried again
    onAdded()
    if (problems.length) throw new Error(problems.join(' '))
  }, hasNote && files.length ? 'Note added and file attached.' : files.length ? 'File attached.' : 'Note added.')

  const label = !notes ? (files.length > 1 ? 'Attach files' : 'Attach file')
    : hasNote && files.length ? 'Add note & attach' : files.length ? (files.length > 1 ? 'Attach files' : 'Attach file') : 'Add note'

  return (
    <div className="add-note-box" style={{ marginBottom: 16 }}>
      <label className="cap" htmlFor={`note-${kind}`}>{notes ? 'Add a note' : 'Attach a file'}</label>
      {notes && <textarea id={`note-${kind}`} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add an update or a question…" />}
      {files.length > 0 && (
        <div className="chips">
          {files.map((f, i) => (
            <span className="chip" key={`${f.name}-${i}`}>{f.name} ({fmtSize(f.size)})
              <button type="button" aria-label={`Remove ${f.name}`} onClick={() => setFiles((cur) => cur.filter((_, j) => j !== i))}>×</button>
            </span>
          ))}
        </div>
      )}
      <div className="add-note-actions">
        <span style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          {canAttach && (
            <>
              <input ref={input} type="file" multiple hidden onChange={pick} aria-label="Choose files to attach"
                accept={info.data.allowed_extensions.map((x) => `.${x}`).join(',')} />
              <button type="button" className="btn2" disabled={busy} onClick={() => input.current.click()}>📎 Attach file</button>
            </>
          )}
          {notes && staff && (
            <label className="checkrow"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note (hidden from the {ownerLabel})</label>
          )}
        </span>
        <button className="btn" disabled={busy || (!hasNote && !files.length)} onClick={submit}>{busy ? 'Working…' : label}</button>
      </div>
      {canAttach && <small style={{ display: 'block', marginTop: 8, fontSize: 11, color: 'var(--muted)' }}>
        Images and documents (png, jpg, gif, webp, pdf, txt, csv, doc, docx, xls, xlsx, ppt, pptx), up to 1 MB each.
      </small>}
    </div>
  )
}

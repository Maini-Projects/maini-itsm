import { useEffect, useState } from 'react'
import { api } from '../api'
import { Empty, ErrorBox, Loading, Pager, fmtDate, useDebounced, useFetch } from '../components/ui'

const LIMIT = 50
const KEEP = [[1, '1 day'], [3, '3 days'], [7, '7 days'], [10, '10 days'], [30, '30 days'], [60, '60 days'], [90, '90 days'], [180, '6 months'], [365, '1 year']]
const TABLES = [['incidents', 'Incidents'], ['problems', 'Problems'], ['defects', 'Defects'], ['changes', 'Changes'], ['releases', 'Releases'], ['approvals', 'Approvals'], ['profiles', 'Users'], ['sla_policies', 'SLA targets']]

export default function Audit() {
  const [table, setTable] = useState('')
  const [record, setRecord] = useState('')
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [offset, setOffset] = useState(0)
  const [keep, setKeep] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const dr = useDebounced(record)
  useEffect(() => { api.get('/audit/settings').then((s) => setKeep(s.retention_days)).catch(() => setKeep(10)) }, [])
  const saveKeep = async (days) => {
    setSaveError(null)
    try { await api.put('/audit/settings', { days }); setKeep(days) } catch (e) { setSaveError(e) }
  }
  const users = useFetch(() => api.get('/users'))
  useEffect(() => setOffset(0), [table, dr, action, actor, since, until])
  const { data, error, loading } = useFetch(
    () => api.get('/audit', {
      table, record: dr.trim(), action, actor_id: actor,
      since: since ? new Date(since).toISOString() : undefined,
      until: until ? new Date(`${until}T23:59:59`).toISOString() : undefined,
      limit: LIMIT, offset,
    }),
    [table, dr, action, actor, since, until, offset, keep],
  )
  const change = (r) => (r.old_status !== r.new_status ? [r.old_status, r.new_status] : [r.changed_fields?.length ? `Fields: ${r.changed_fields.join(', ')}` : '—', ''])
  return (
    <>
      <div className="eyebrow">Audit & Compliance</div>
      <h2 className="title">Audit History</h2>
      <p className="sub">Who changed what, and when. This log is written by the database itself and cannot be edited. Only entries from the selected period are shown.</p>
      <div className="toolbar">
        <div className="filters">
          <input placeholder="Record, e.g. INC-10001" value={record} onChange={(e) => setRecord(e.target.value)} aria-label="Record number" />
          <select value={table} onChange={(e) => setTable(e.target.value)} aria-label="Type"><option value="">All record types</option>{TABLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <select value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action"><option value="">All actions</option><option value="INSERT">Created</option><option value="UPDATE">Updated</option><option value="DELETE">Deleted</option></select>
          <select value={actor} onChange={(e) => setActor(e.target.value)} aria-label="User"><option value="">All users</option>{(users.data || []).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select>
          <label>From <input type="date" value={since} onChange={(e) => setSince(e.target.value)} /></label>
          <label>To <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
        </div>
      </div>
      <div className="toolbar"><label>Keep audit logs for{' '}
        <select value={keep ?? 10} onChange={(e) => saveKeep(Number(e.target.value))} aria-label="Keep audit logs for">{KEEP.map(([d, l]) => <option key={d} value={d}>{l}{d === 10 ? ' (default)' : ''}</option>)}</select>
      </label></div>
      <ErrorBox error={saveError} />
      <ErrorBox error={error} />
      <div className="card table">
        <table>
          <thead><tr><th>Timestamp</th><th>User</th><th>Action</th><th>Record</th><th>Previous</th><th>New</th></tr></thead>
          <tbody>
            {data?.items.map((r) => {
              const [prev, next] = change(r)
              return (
                <tr key={r.id}>
                  <td>{fmtDate(r.at)}</td><td>{r.actor_name || 'System'}</td><td>{r.summary}</td><td>{r.record || '—'}</td><td>{prev || '—'}</td><td>{next || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {loading && !data && <Loading />}
        {data && !data.items.length && <Empty>No audit entries match.</Empty>}
        {data && <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
      </div>
    </>
  )
}

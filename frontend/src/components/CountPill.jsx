import { useAuth } from '../auth'

function countFor(key, c) {
  if (!c) return null
  if (key === 'incidents') return c.incidents?.open
  if (key === 'problems') return c.problems ? Object.values(c.problems).reduce((a, b) => a + b, 0) : null
  if (key === 'defects') return c.defects?.open
  if (key === 'changes') return c.changes?.active
  if (key === 'releases') return c.releases?.upcoming_14_days
  if (key === 'approvals') return c.pending_approvals ? c.pending_approvals.total + (c.pending_signups || 0) : null
  return null
}

const LABEL = { incidents: 'open', defects: 'open', problems: 'in total', changes: 'active', releases: 'upcoming', approvals: 'pending' }

// The open count shown beside a page's heading, for example "Incident Management  2".
export default function CountPill({ of }) {
  const { counts } = useAuth()
  const n = countFor(of, counts)
  if (n === null || n === undefined) return null
  return <span className="pagecount"><b>{n}</b> {LABEL[of]}</span>
}

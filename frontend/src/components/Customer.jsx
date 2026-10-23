import { useAuth } from '../auth'

export const ProjectFilter = ({ cust, value, onChange }) => !cust.canPick ? null : (
  <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Project">
    <option value="">Project</option>
    {cust.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
  </select>
)

// Rows carry their customer's project_id; the Customer column (shown when several customers are selected) names it.
export function useCustomers() {
  const { me } = useAuth()
  const projects = me.projects || []
  const multi = (me.active_project_ids || []).length > 1
  const of = (row) => projects.find((p) => p.id === row.project_id)?.name || '—'
  return { multi, of, projects, canPick: multi && me.role !== 'employee' }
}

import { Link, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import { IncidentDetail, IncidentList } from './pages/Incidents'
import { ProblemDetail, ProblemList } from './pages/Problems'
import { ChangeDetail, ChangeList } from './pages/Changes'
import { ReleaseDetail, ReleaseList } from './pages/Releases'
import Approvals from './pages/Approvals'
import { Services, Sla } from './pages/Portfolio'
import { ReportView, Reports } from './pages/Reports'
import Audit from './pages/Audit'
import Admin from './pages/Admin'

function Guard({ area, children }) {
  const { me } = useAuth()
  if (!me.menu.includes(area)) {
    return <div className="card"><div className="empty">Your role does not have access to this area. <Link to="/" className="link">Go to the dashboard</Link></div></div>
  }
  return children
}

const NotFound = () => (
  <div className="card"><div className="empty">That page does not exist. <Link to="/" className="link">Go to the dashboard</Link></div></div>
)

export default function App() {
  const { state } = useAuth()
  if (state === 'loading') return <Loading text="Signing you in…" />
  if (state === 'out') return <Login />
  const g = (area, el) => <Guard area={area}>{el}</Guard>
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="incidents" element={g('incidents', <IncidentList />)} />
        <Route path="incidents/:id" element={g('incidents', <IncidentDetail />)} />
        <Route path="problems" element={g('problems', <ProblemList />)} />
        <Route path="problems/:id" element={g('problems', <ProblemDetail />)} />
        <Route path="changes" element={g('changes', <ChangeList />)} />
        <Route path="changes/:id" element={g('changes', <ChangeDetail />)} />
        <Route path="releases" element={g('releases', <ReleaseList />)} />
        <Route path="releases/:id" element={g('releases', <ReleaseDetail />)} />
        <Route path="approvals" element={g('approvals', <Approvals />)} />
        <Route path="services" element={g('services', <Services />)} />
        <Route path="sla" element={g('sla', <Sla />)} />
        <Route path="reports" element={g('reports', <Reports />)} />
        <Route path="reports/:key" element={g('reports', <ReportView />)} />
        <Route path="audit" element={g('audit', <Audit />)} />
        <Route path="admin" element={g('admin', <Admin />)} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

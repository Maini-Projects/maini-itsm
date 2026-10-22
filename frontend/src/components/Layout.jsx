import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { roleLabel } from './ui'
import ProjectPicker from './ProjectPicker'

const SECTIONS = [
  { title: 'Service Management', items: [['incidents', 'Incidents'], ['problems', 'Problems'], ['defects', 'Defects'], ['changes', 'Changes'], ['releases', 'Releases']] },
  { title: 'Application Portfolio', items: [['services', 'Applications']] },
  { title: 'Governance & Operations', items: [['approvals', 'Approvals'], ['sla', 'SLA Management'], ['reports', 'Reports'], ['audit', 'Audit History']] },
  { title: 'Administration', items: [['admin', 'Admin'], ['projects', 'Projects']] },
]

export default function Layout() {
  const { me, signOut, refreshCounts, reloadMe } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false) // small screens: the slide-in menu
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('itsm.sidebar') === 'collapsed' } catch { return false } })
  const [menu, setMenu] = useState(false)
  const [search, setSearch] = useState('')
  const [now, setNow] = useState(new Date())
  const activeIds = me.active_project_ids || []
  const [picked, setPicked] = useState(activeIds)
  useEffect(() => setPicked(me.active_project_ids || []), [me.active_project_ids])
  const applyProjects = async () => {
    const next = picked.length ? picked : me.projects.map((p) => p.id) // at least one project stays selected
    if (next.length === activeIds.length && next.every((id) => activeIds.includes(id))) { setPicked(activeIds); return }
    try { localStorage.setItem('itsm.project', next.join(',')) } catch { /* not remembered */ }
    const parts = location.pathname.split('/')
    if (parts.length > 2 && parts[1] !== 'reports') navigate(`/${parts[1]}`) // a record page -> its list
    await reloadMe() // the page below remounts and loads the chosen projects' data
    refreshCounts()
  }

  useEffect(() => { const t = setInterval(() => setNow(new Date()), 30000); return () => clearInterval(t) }, [])
  useEffect(() => { setOpen(false); setMenu(false); refreshCounts() }, [location.pathname, refreshCounts])

  const toggleMenu = () => {
    if (window.matchMedia('(max-width: 850px)').matches) { setOpen((o) => !o); return }
    setCollapsed((c) => {
      try { localStorage.setItem('itsm.sidebar', c ? 'open' : 'collapsed') } catch { /* the choice just is not remembered */ }
      return !c
    })
  }

  const initials = me.full_name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
  const clock = now.toLocaleString(undefined, { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
  const goSearch = (e) => {
    e.preventDefault()
    if (search.trim()) navigate(`/incidents?q=${encodeURIComponent(search.trim())}`)
  }

  return (
    <>
      <header className="top">
        <button className="hamb" onClick={toggleMenu} aria-label="Toggle menu" aria-expanded={!collapsed}>☰</button>
        <Link className="brand" to="/" title="Go to Home">
          <img src="/logo.png" alt="" /><span className="brand-text">MAINI CONSULTING</span>
        </Link>
        <form className="search" onSubmit={goSearch} role="search">
          ⌕ <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search" aria-label="Search incidents" />
        </form>
        <div className="actions">
          {me.projects?.length ? (
            <ProjectPicker compact projects={me.projects} picked={picked} onChange={setPicked} onClose={applyProjects} />
          ) : me.role === 'employee' && me.organization_name ? <div className="time org-name">{me.organization_name}</div> : null}
          <Link className="home-btn" to="/" title="Home" aria-label="Home">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 11.5 12 4l9 7.5" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" /></svg>
          </Link>
          <div className="time">{clock}</div>
          <button className="avatar" onClick={() => setMenu((m) => !m)} aria-label="Account menu"><span>{initials}</span></button>
        </div>
        {menu && (
          <div className="usermenu">
            <div className="who"><b>{me.full_name}</b><span>{me.email}<br />{roleLabel(me.role)}{me.team_name ? ` · ${me.team_name} team` : ''}</span></div>
            <button onClick={() => { setMenu(false); navigate('/account') }}>Account settings</button>
            <button onClick={signOut}>Sign out</button>
          </div>
        )}
      </header>

      <div className={`shell ${collapsed ? 'nosidebar' : ''}`}>
        <aside className={open ? 'open' : ''}>
          {SECTIONS.map((sec) => {
            const items = sec.items.filter(([key]) => me.menu.includes(key))
            if (!items.length) return null
            return (
              <div key={sec.title}>
                <div className="side-title">{sec.title}</div>
                <div className="nav-group">
                  {items.map(([key, label]) => {
                    return (
                      <NavLink key={key} to={`/${key}`} className={({ isActive }) => `nav ${isActive ? 'active' : ''}`}>
                        <span className="menu-label">{label}</span>
                        <span className="chev">›</span>
                      </NavLink>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </aside>
        <div>
          <section className="hero"><div className="in">
            <h1>AI-Powered Managed Services Support</h1>
          </div></section>
          <main className="content" key={(me.active_project_ids || []).join(',')}><Outlet /></main>
        </div>
      </div>
    </>
  )
}

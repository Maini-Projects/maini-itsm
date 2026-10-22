import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import ChangePassword from './ChangePassword'
import { roleLabel } from './ui'

const SECTIONS = [
  { title: 'Service Management', items: [['incidents', 'Incidents'], ['problems', 'Problems'], ['defects', 'Defects'], ['changes', 'Changes'], ['releases', 'Releases']] },
  { title: 'Application Portfolio', items: [['services', 'Applications']] },
  { title: 'Governance & Operations', items: [['approvals', 'Approvals'], ['sla', 'SLA Management'], ['reports', 'Reports'], ['audit', 'Audit History']] },
  { title: 'Administration', items: [['admin', 'Admin']] },
]

export default function Layout() {
  const { me, signOut, refreshCounts } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false) // small screens: the slide-in menu
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('itsm.sidebar') === 'collapsed' } catch { return false } })
  const [menu, setMenu] = useState(false)
  const [pw, setPw] = useState(false)
  const [search, setSearch] = useState('')
  const [now, setNow] = useState(new Date())

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
          {me.organization_name && <div className="time org-name">{me.organization_name}</div>}
          <div className="time">{clock}</div>
          <button className="avatar" onClick={() => setMenu((m) => !m)} aria-label="Account menu"><span>{initials}</span></button>
        </div>
        {menu && (
          <div className="usermenu">
            <div className="who"><b>{me.full_name}</b><span>{me.email}<br />{roleLabel(me.role)}{me.team_name ? ` · ${me.team_name} team` : ''}</span></div>
            <button onClick={() => { setMenu(false); navigate('/account') }}>Account settings</button>
            <button onClick={() => { setMenu(false); setPw(true) }}>Change password</button>
            <button onClick={signOut}>Sign out</button>
          </div>
        )}
      </header>

      <div className={`shell ${collapsed ? 'nosidebar' : ''}`}>
        <aside className={open ? 'open' : ''}>
          <NavLink to="/" end className={({ isActive }) => `sidebar-home ${isActive ? 'active' : ''}`}><span>Dashboard Home</span><span>›</span></NavLink>
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
          <main className="content"><Outlet /></main>
        </div>
      </div>
      {pw && <ChangePassword onClose={() => setPw(false)} />}
    </>
  )
}

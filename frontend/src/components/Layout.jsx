import { NavLink, useNavigate } from 'react-router-dom'
import { clearToken } from '../lib/auth'
import {
  Newspaper, Globe, Bot, Zap, ScrollText, LogOut, Settings, Radio
} from 'lucide-react'
import clsx from 'clsx'

const NAV = [
  { to: '/',          label: 'Dashboard',   icon: Zap },
  { to: '/pipelines', label: 'Pipelines',   icon: Radio },
  { to: '/agents',    label: 'Agentes',     icon: Bot },
  { to: '/sites',     label: 'Sitios WP',   icon: Globe },
  { to: '/llm',       label: 'Modelos LLM', icon: Settings },
  { to: '/logs',      label: 'Logs',        icon: ScrollText },
]

export default function Layout({ children }) {
  const navigate = useNavigate()

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-5 border-b border-slate-800 flex items-center gap-2">
          <Newspaper size={20} className="text-blue-400" />
          <span className="font-bold text-white text-sm tracking-wide">AutoReporter</span>
          <span className="ml-auto text-xs text-slate-500 font-mono">v2</span>
        </div>
        <nav className="flex-1 p-3 space-y-0.5">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                isActive
                  ? 'bg-blue-600 text-white font-medium'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              )}
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={handleLogout}
          className="m-3 flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-red-400 hover:bg-slate-800 transition-colors"
        >
          <LogOut size={16} />
          Cerrar sesión
        </button>
      </aside>

      {/* Content */}
      <main className="flex-1 overflow-y-auto bg-slate-950">
        {children}
      </main>
    </div>
  )
}

import { type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Gestiolibra</h1>
        <nav>
          <NavLink to="/agenda" className={({ isActive }) => isActive ? 'active' : ''}>
            Agenda
          </NavLink>
          <NavLink to="/clientes" className={({ isActive }) => isActive ? 'active' : ''}>
            Clientes
          </NavLink>
          {user?.role === 'admin' && (
            <NavLink to="/dashboard" className={({ isActive }) => isActive ? 'active' : ''}>
              Dashboard
            </NavLink>
          )}
        </nav>
        <div className="user-info">
          <span>{user?.name} ({user?.role})</span>
          <button onClick={() => logout()}>Salir</button>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  )
}

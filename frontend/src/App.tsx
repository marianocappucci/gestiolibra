import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './context/AuthContext'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { ForgotPassword, ResetPassword } from './pages/PasswordReset'
import { Agenda } from './pages/Agenda'
import { Clientes } from './pages/Clientes'
import { Dashboard } from './pages/Dashboard'
import { Usuarios } from './pages/Usuarios'
import { Logs } from './pages/Logs'
import { Configuracion } from './pages/Configuracion'

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Cargando…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Públicas a propósito: quien las necesita no puede iniciar sesión. */}
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route
        path="/agenda"
        element={
          <ProtectedRoute>
            <Agenda />
          </ProtectedRoute>
        }
      />
      <Route
        path="/clientes"
        element={
          <ProtectedRoute>
            <Clientes />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reportes"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      {/* La pantalla suelta de Facturación se borró el 2026-08-22: lo único
          que tenía era el formulario de ARCA, que ya vive dentro de
          Configuración (`SECCION_ARCA` de libra-ui) — eran dos pantallas
          para el mismo `GET/PUT /config/arca`. La ruta sobrevive como
          redirección y no se borra: sin ella un favorito viejo cae en el
          catch-all y aterriza en la agenda sin explicación. */}
      {/* 🔴 El destino cambio el 2026-08-30 con la Configuracion canonica:
          ARCA dejo de ser una pestana de primer nivel y paso a ser una
          SUB-SECCION de "Integraciones", junto a MercadoPago y el correo. Con
          el `?seccion=arca` viejo la redireccion sigue funcionando --no da
          error-- pero aterriza en la primera pestana, que es Empresa: el
          favorito lleva a otro lado y nadie se entera. */}
      <Route
        path="/facturacion"
        element={
          <Navigate to="/configuracion?seccion=integraciones&integracion=arca" replace />
        }
      />
      <Route
        path="/usuarios"
        element={
          <ProtectedRoute>
            <Usuarios />
          </ProtectedRoute>
        }
      />
      {/* El gateo real es del backend (`admin_only` sobre `/logs`): acá
          `adminOnly` sólo esconde el ítem del menú. Un staff que escriba la
          URL a mano ve el error del 403, no los datos. */}
      <Route
        path="/logs"
        element={
          <ProtectedRoute>
            <Logs />
          </ProtectedRoute>
        }
      />
      {/* Una sola ruta para las cuatro secciones: la activa va en
          `?seccion=`, así se puede linkear una en particular. */}
      <Route
        path="/configuracion"
        element={
          <ProtectedRoute>
            <Configuracion />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/agenda" replace />} />
    </Routes>
  )
}

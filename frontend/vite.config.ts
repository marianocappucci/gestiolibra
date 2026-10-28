import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Proxy de API en dev: mismo origen que el front (localhost:5173) hacia
// el backend FastAPI (localhost:8000) para que la cookie de sesion
// (gl_session) funcione sin lidiar con CORS/SameSite cross-origin --
// mismo truco que se usa en produccion, donde el build de este frontend
// se sirve desde el mismo proceso FastAPI (ver app/asgi.py).
const API_PATHS = [
  '/auth', '/branches', '/resources', '/services', '/clients',
  '/business', '/users', '/reminders', '/deposits', '/config',
  '/dashboard', '/appointments', '/health',
  // El tema de la suite (libra-ui ADR-008): `cargarTema()` lo pide al arrancar, tiene que llegar al backend también en desarrollo.
  '/api/tema',
  // La cola de ARCA, los turnos a revisar y el estado del nodo (ADR-036), y la pantalla «Sucursal sin internet» (libra-ui ADR-080).
  '/api/nodo', '/api/nodos-offline',
  // El registro de errores del navegador (libra-ui ADR-053): `instalarReporteDeErrores` y `<ErrorBoundary>` postean acá.
  '/api/errores-cliente',
  // El PDF de la factura y de su nota de crédito (`GET /api/facturas/{id}/pdf`, del motor).
  '/api/facturas',
  // La configuración de los avisos por WhatsApp y mail y su registro (`/api/avisos`, del motor; ADR-040).
  '/api/avisos',
]

// Las claves del proxy se emiten como regex (Vite trata como RegExp toda
// clave que empieza con `^`) que exige que el path TERMINE ahi o siga con
// `/`. Con el match por prefijo simple de antes, una ruta de la SPA que
// EMPIEZA igual que un prefijo de la API quedaba secuestrada por el proxy y
// el navegador recibia el JSON del backend en vez de la pagina.
//
// Hoy este producto no tiene ninguna colision (`/clientes` vs `/clients`
// difieren antes del final), asi que esto es preventivo: la trampa se
// activaria sola al agregar una ruta como `/configuracion` (capturada por
// `/config`) o `/dashboard-x`. Es lo que paso en VentaLibra el 2026-07-28
// con `/catalogo` y `/config-arca` -- ver
// wiki/concepts/estandares-desarrollo.md.
//
// Solo afecta al dev server: en produccion sirve FastAPI, que matchea rutas
// exactas y deja caer esos paths al catch-all de la SPA.
const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: Object.fromEntries(
      API_PATHS.map((apiPath) => [
        `^${escapeRegex(apiPath)}(?:/|$)`,
        { target: 'http://localhost:8000', changeOrigin: true },
      ]),
    ),
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy de API en dev: mismo origen que el front (localhost:5173) hacia
// el backend FastAPI (localhost:8000) para que la cookie de sesion
// (gl_session) funcione sin lidiar con CORS/SameSite cross-origin --
// mismo truco que se usa en produccion, donde el build de este frontend
// se sirve desde el mismo proceso FastAPI (ver app/asgi.py).
const API_PATHS = [
  '/auth', '/branches', '/resources', '/services', '/clients',
  '/business', '/users', '/reminders', '/deposits', '/config',
  '/dashboard', '/appointments', '/health',
]

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      API_PATHS.map((path) => [path, { target: 'http://localhost:8000', changeOrigin: true }]),
    ),
  },
})

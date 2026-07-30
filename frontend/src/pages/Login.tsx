// Shim sobre libra-ui/Login (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo branding/redirectTo -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import { createLogin } from 'libra-ui/Login'

export const Login = createLogin({
  productName: 'Gestiolibra',
  productInitial: 'G',
  redirectTo: '/agenda',
  // Muestra el enlace "¿Olvidaste tu contraseña?". Va de la mano con
  // `incluir_password_reset=True` en app/routers/auth.py: sin el backend
  // prendido, este enlace llevaría a una pantalla que no puede funcionar.
  forgotPasswordPath: '/forgot-password',
})

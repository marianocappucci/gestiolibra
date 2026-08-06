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
  // Boton "Entrar a la demo" -- va de la mano con incluir_demo=True en
  // app/routers/auth.py. Declararlo aca NO alcanza para que se muestre:
  // libra-ui consulta GET /auth/demo al montar y solo lo pinta si la
  // instancia contesta que es una demo.
  demoPath: '/auth/demo',
})

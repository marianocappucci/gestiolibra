// Shim sobre libra-ui/PasswordReset (mismo patrón que Login/Usuarios).
// Las dos pantallas de recuperación son públicas: van fuera de
// ProtectedRoute en App.tsx, porque quien las usa justamente no puede entrar.
import { createForgotPassword, createResetPassword } from 'libra-ui/PasswordReset'

const branding = { productName: 'Gestiolibra', productInitial: 'G' }

// Con `captcha=True` libraauth exige el captcha tambien en forgot-password (sin
// el, ese endpoint manda correos a pedido de cualquiera). El reset-password no
// lo lleva: ya viaja con el token del correo.
export const ForgotPassword = createForgotPassword({ ...branding, captchaPath: '/auth/captcha' })
export const ResetPassword = createResetPassword(branding)

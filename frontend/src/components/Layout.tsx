// Shim sobre libra-ui/Layout (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo NAV_ITEMS/branding -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import { CalendarDays, HandCoins, LayoutDashboard, ScrollText, Settings, UserCog, Users } from 'lucide-react'
import { createLayout, type NavSection } from 'libra-ui/Layout'
import { WORDMARK } from '@/branding'

// ⚠️ No hay ítem «Facturación» a propósito: la configuración de ARCA vive dentro de Configuración (pedido del humano, 2026-08-22).
// Dashboard va primero (pedido del humano, 2026-08-22) y es `adminOnly`: el catch-all de `App.tsx` sigue mandando a `/agenda`.
// Menú en dos niveles (sección + ítems), la forma de Contalibra y VentaLibra (ADR-054 de VentaLibra, 2026-10-01).
const NAV_SECCIONES: NavSection<{ role?: string; name?: string }>[] = [
  { items: [{ to: '/reportes', label: 'Dashboard', icon: LayoutDashboard, adminOnly: true }] },
  {
    label: 'Atención',
    items: [
      { to: '/agenda', label: 'Agenda', icon: CalendarDays },
      // Junto a la Agenda: una seña se pide desde un turno y se cobra acá. `adminOnly` porque el listado y el cobro lo son
      // en el backend. ⚠️ Sin `module: 'senas'` a propósito: este producto no le pasa `hasModule` al Layout.
      { to: '/senas', label: 'Señas', icon: HandCoins, adminOnly: true },
      { to: '/clientes', label: 'Clientes', icon: Users },
    ],
  },
  {
    label: 'Administración',
    items: [
      { to: '/usuarios', label: 'Usuarios', icon: UserCog, adminOnly: true },
      { to: '/logs', label: 'Logs', icon: ScrollText, adminOnly: true },
      { to: '/configuracion', label: 'Configuración', icon: Settings, adminOnly: true },
    ],
  },
]

export const Layout = createLayout({
  productName: 'Gestiolibra',
  productInitial: 'G',
  // La marca (ícono + color del producto) la dibuja libra-ui con `producto` (ADR-033) y el nombre va en Montserrat Bold. Las clases del
  // nombre salen de `@/branding`, el mismo archivo que usa el login: es lo que garantiza que las dos pantallas escriban "Gestiolibra" igual.
  producto: 'gestiolibra',
  // 🔴 El interlineado va PEGADO al tamano (`/[17px]`) y no como `leading-*`
  // aparte: en Tailwind v4 una utilidad de tamano emite tambien `line-height`,
  // asi que el `leading-none` que libra-ui pone por defecto perderia contra
  // este `text-[15px]` y el nombre se quedaria con 22,5 px de caja.
  // 17 = 32 (el alto de `MarcaProducto`) menos los 15 de la linea de la empresa.
  wordmarkClassName: `${WORDMARK} text-[15px]/[17px]`,
  // 🔴 **Dashboard va primero**, pedido del humano (2026-08-22). Es la pantalla
  // de resumen: lo que se abre para saber cómo viene el día antes de entrar a
  // operar. Ojo con leerlo como "es la pantalla de arranque": el ítem es
  // `adminOnly`, así que un usuario `staff` no lo ve, y por eso el catch-all de
  // `App.tsx` sigue mandando a `/agenda` y no acá.
  navSections: NAV_SECCIONES,
  // El nombre del negocio, debajo del nombre del producto (viene de Configuración > Datos de empresa, vía `/auth/me`).
  getUserSubtitle: (u) => (u as { empresa_nombre?: string }).empresa_nombre,
})

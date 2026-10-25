// Shim sobre libra-ui/Layout (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo NAV_ITEMS/branding -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import { createLayout, type NavSection } from 'libra-ui/Layout'
import { ICONOS } from 'libra-ui/iconos-identidad'
import { RUTA_COLA_DEL_NODO, TITULO_COLA } from 'libra-ui/cola-del-nodo'
import { useConexionDelNodo } from 'libra-ui/nodo-offline'
import { useAuth } from '@/context/AuthContext'
import { WORDMARK } from '@/branding'

type Usuario = { role?: string; name?: string; esNodo?: boolean }

/** El cartel de arriba cuando el equipo del local está sin conexión (libra-ui ADR-077 y ADR-094, ADR-036 de este producto).
 *
 *  🔴 **No es el texto del kit para los productos que encolan.** `TEXTO_CARTEL_SIN_CONEXION_CON_COLA` habla de cartas de porte y de
 *  «CPE válida para viajar»: es de LibraCargo. Acá no hay camiones: se atiende y se cobra, y la factura queda para después. */
const TEXTO_CARTEL_SIN_CONEXION =
  'Sin conexión: la agenda es de consulta. Podés atender y cobrar los turnos: el cliente se lleva un comprobante no fiscal y las facturas quedan en cola y se emiten solas al volver.'

/** La sesión, más si esta instalación es el nodo del local (LibraEdge).
 *
 *  Lo sabe el cartel de `conexionDelNodo`, que consulta; acá sólo se lee. Es lo que deja que el menú muestre «Cola de
 *  comprobantes» únicamente en un nodo (`hideFor` más abajo): `NAV_SECCIONES` es un array de módulo y no puede preguntar por hooks,
 *  pero `useAuth` sí corre dentro del sidebar. */
function useAuthConNodo() {
  const sesion = useAuth() as unknown as { user: Usuario | null; logout: () => Promise<void> }
  const { esNodo } = useConexionDelNodo()
  return { ...sesion, user: sesion.user ? { ...sesion.user, esNodo } : null }
}

// ⚠️ No hay ítem «Facturación» a propósito: la configuración de ARCA vive dentro de Configuración (pedido del humano, 2026-08-22).
// Dashboard va primero (pedido del humano, 2026-08-22) y es `adminOnly`: el catch-all de `App.tsx` sigue mandando a `/agenda`.
// Menú en dos niveles (sección + ítems), la forma de Contalibra y VentaLibra (ADR-054 de VentaLibra, 2026-10-01).
const NAV_SECCIONES: NavSection<Usuario>[] = [
  { items: [{ to: '/reportes', label: 'Dashboard', icon: ICONOS.dashboard, adminOnly: true }] },
  {
    label: 'Atención',
    items: [
      { to: '/agenda', label: 'Agenda', icon: ICONOS.agenda },
      // Junto a la Agenda: una seña se pide desde un turno y se cobra acá. `adminOnly` porque el listado y el cobro lo son
      // en el backend. ⚠️ Sin `module: 'senas'` a propósito: este producto no le pasa `hasModule` al Layout.
      { to: '/senas', label: 'Señas', icon: ICONOS.senas, adminOnly: true },
      { to: '/clientes', label: 'Clientes', icon: ICONOS.clientes },
      // La cola de ARCA del nodo (libra-ui ADR-094): las facturas de los turnos cobrados sin conexión, que salen solas al volver.
      // **Sólo se ve en un nodo** (`hideFor`): en la web y en una instancia común no hay cola y el menú queda como siempre.
      // Sin `adminOnly`: el mostrador la mira; reintentar, descartar y marcar emitido son de admin en el backend.
      { to: '/cola', label: TITULO_COLA, icon: ICONOS.comprobantesAFacturar,
        hideFor: (u) => !u.esNodo },
    ],
  },
  {
    label: 'Administración',
    items: [
      { to: '/usuarios', label: 'Usuarios', icon: ICONOS.usuarios, adminOnly: true },
      { to: '/logs', label: 'Logs', icon: ICONOS.logDeActividad, adminOnly: true },
      { to: '/configuracion', label: 'Configuración', icon: ICONOS.configuracion, adminOnly: true },
    ],
  },
]

export const Layout = createLayout<Usuario>({
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
  // La barra de estado del pie (libra-ui ADR-083, libracore ADR-075): usuario, ARCA, respaldo y versión, de
  // `GET /api/estado-del-sistema` al cargar y cada pocos minutos.
  barraDeEstado: true,
  getUserSubtitle: (u) => (u as { empresa_nombre?: string }).empresa_nombre,
  // El cartel «Sin conexión» arriba del contenido, sólo en un nodo y sólo sin conexión (libra-ui ADR-077/ADR-094).
  // 🔑 `ruta` es la de la cola y no la `/api/nodo/conexion` de siempre: este producto no monta esa (es del punto de venta de
  // ContaLibra y RestoLibra), y la cola contesta lo mismo que el cartel lee (`es_nodo`, `en_linea`, `node_id`). `limite=1` porque
  // acá sólo importa la cabecera. Fuera de un nodo contesta `es_nodo: false`, el cartel deja de consultar y no se dibuja nada.
  conexionDelNodo: { ruta: `${RUTA_COLA_DEL_NODO}?limite=1`, texto: TEXTO_CARTEL_SIN_CONEXION },
  useAuth: useAuthConNodo,
})

// La cola de comprobantes del nodo: las facturas de los turnos cobrados sin conexión que todavía no salieron en ARCA.
//
// Es `BandejaDeLaCola` del kit (libra-ui ADR-094) y Gestiolibra sólo le pone lo suyo: quién puede resolver y cómo se llama cada
// pedido. No hay `BandejaDeComprobantes` en este producto (no recibe comprobantes de otros sistemas), así que la cola va en su propia
// pantalla.
//
// 🔑 **Sólo tiene sentido en un nodo.** El menú la muestra únicamente ahí (`Layout.tsx`); si alguien escribe `/cola` en otra instancia,
// el panel contesta «esta instalación no es un nodo» por su cuenta, sin romper nada.
//
// Reintentar, descartar y marcar emitido deciden sobre un documento fiscal: `puedeResolver` es sólo de admin, igual que el backend
// (`build_cola_del_nodo_router(resolver_con=require_admin)` en `app/main.py`). El mostrador la mira y puede pedir «Emitir ahora».
import { BandejaDeLaCola } from 'libra-ui/BandejaDeLaCola'
import { ETIQUETA_DE_TIPO, type PedidoDeCola } from 'libra-ui/cola-del-nodo'

import { useAuth } from '@/context/AuthContext'

type FotoDelPedido = { servicio?: string; cliente?: { nombre?: string } }

/** El título de cada tarjeta: «Factura · Corte · Ana Gómez». El `origen_id` es el id del turno (un uuid que nadie reconoce), así que se
 *  nombra por lo que se cobró: la foto que guardó la cola (`datos`) trae el servicio y el cliente tal como estaban. */
export function describirPedido(pedido: PedidoDeCola): string {
  const tipo = ETIQUETA_DE_TIPO[pedido.origen_tipo] ?? pedido.origen_tipo
  const foto = pedido.datos as FotoDelPedido
  return [tipo, foto.servicio, foto.cliente?.nombre].filter(Boolean).join(' · ')
}

export function Cola() {
  const { user } = useAuth()
  return <BandejaDeLaCola puedeResolver={user?.role === 'admin'} describir={describirPedido} />
}

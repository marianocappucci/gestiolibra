// Las cuentas chicas de la factura de un turno y su nota de crédito (`components/agenda/factura-del-turno.tsx`, ADR-039). Viven
// acá, y no en el componente, para poder probarlas solas y para que el archivo del componente exporte sólo componentes.
import { TIPO_COMPROBANTE_LABELS, type ComprobanteDelTurno } from '../api'

/** Lo mismo que pide el backend (`MOTIVO_MINIMO` y `MOTIVO_MAXIMO` en `routers/factura_del_turno.py`). */
export const MOTIVO_MINIMO = 5
export const MOTIVO_MAXIMO = 200

export const tieneCae = (c: ComprobanteDelTurno) => Boolean(c.cae) && c.cae !== 'PENDIENTE'

/** `Factura B 0001-00000012`. */
export function etiquetaDeComprobante(c: ComprobanteDelTurno): string {
  const numero = `${String(c.punto_venta).padStart(4, '0')}-${String(c.numero).padStart(8, '0')}`
  return `${TIPO_COMPROBANTE_LABELS[c.tipo] ?? 'Comprobante'} ${numero}`
}

/** El importe que escribió una persona (`1500,50` o `1500.50`) como número, o `null` si no es un monto de hasta dos decimales. */
export function importeEscrito(texto: string): number | null {
  const limpio = texto.trim().replace(',', '.')
  if (!/^\d+(\.\d{1,2})?$/.test(limpio)) return null
  const n = Number(limpio)
  return n > 0 ? n : null
}

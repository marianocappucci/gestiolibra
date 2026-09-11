/** Lo que la pantalla de Señas y el detalle del turno comparten, menos los
 *  componentes (que viven en `components/senas.tsx`: un archivo que exporta
 *  componentes y constantes a la vez rompe el fast refresh de Vite).
 *
 *  Una seña se opera desde dos lugares —la lista, para quien cobra, y el turno,
 *  para quien atiende— y los dos tienen que decir lo mismo con las mismas
 *  palabras: el mismo tono para "Pendiente" y el mismo formato de monto.
 */
import { useEffect, useState } from 'react'
import type { TonoEstado } from 'libra-ui/badge-estado'
import { api, type EstadoSena, type MedioPago } from '../api'

/** 🔴 **La pendiente es `atencion`, no `neutro`.** Es la única que pide que
 *  alguien haga algo — cobrarla —, y en una lista de veinte tiene que saltar a
 *  la vista. La devuelta sí es neutra: es un caso cerrado, la plata volvió. */
export const SENA_TONO: Record<EstadoSena, TonoEstado> = {
  pending: 'atencion',
  paid: 'ok',
  failed: 'negativo',
  refunded: 'neutro',
}

/** `$ 1.000,50`. El monto llega como string (`Decimal` del backend). */
export function formatMonto(monto: string | number): string {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' })
    .format(Number(monto))
}

/** El nombre de un medio de pago a partir de su id, con el id como respaldo:
 *  una seña vieja puede tener un medio que el catálogo de hoy ya no ofrece, y
 *  mostrar el id es mejor que mostrar nada. */
export function nombreMedio(medios: MedioPago[], id: string | null): string {
  if (!id) return '—'
  return medios.find((m) => m.id === id)?.label ?? id
}

/** Los medios de pago que sirve el motor (`GET /medios-pago`). */
export function useMediosPago(): MedioPago[] {
  const [medios, setMedios] = useState<MedioPago[]>([])
  useEffect(() => {
    api.get<MedioPago[]>('/medios-pago')
      .then((m) => setMedios(Array.isArray(m) ? m : []))
      // Sin catálogo el diálogo de cobro queda sin opciones y no deja
      // confirmar: es preferible a tumbar la pantalla por una lista auxiliar.
      .catch(() => setMedios([]))
  }, [])
  return medios
}

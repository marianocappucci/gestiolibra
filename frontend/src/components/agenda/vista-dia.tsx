/** El día: la rejilla horaria con **una columna por recurso**.
 *
 *  Es el patrón de Google Calendar cuando se miran varios calendarios a la vez,
 *  y acá es además lo que la pantalla tiene que contestar: al entrar a un día ya
 *  se sabe *cuándo* —lo dijeron la semana y el mes—, y lo que falta es **quién
 *  atiende a quién y en qué hueco entra el próximo**. Mezclados en una sola
 *  columna, buscar el hueco del Box 2 obligaría a pescar sus turnos entre los
 *  de los demás.
 *
 *  Vive en el producto y no en `libra-ui/agenda` por el encabezado: qué se dice
 *  de un carril es lo más específico de cada agenda (en LibraDesk, la patente
 *  del vehículo y el botón de la hoja de ruta; acá, la sucursal del recurso).
 *  La rejilla, el reparto de ancho y los colores sí vienen del paquete.
 */
import { RejillaHoraria, type ColumnaRejilla } from 'libra-ui/agenda'
import { Card, CardContent } from '@/components/ui/card'
import type { Resource } from '../../api'
import type { ArmarEvento } from './eventos'
import type { TurnoConRecurso } from './datos'

export function VistaDia({ recursos, turnos, esHoy, comoEvento, nombreSucursal }: {
  recursos: Resource[]
  turnos: TurnoConRecurso[]
  /** Si el día que se muestra es hoy: la rejilla dibuja la línea de la hora
   *  actual sólo entonces. */
  esHoy: boolean
  comoEvento: ArmarEvento
  nombreSucursal: (branchId: string | null) => string | null
}) {
  if (recursos.length === 0) {
    return (
      <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
        No hay recursos activos para agendar.
      </CardContent></Card>
    )
  }

  const columnas: ColumnaRejilla[] = recursos.map((r) => {
    const sucursal = nombreSucursal(r.branch_id)
    return {
      clave: r.id,
      // Todas las columnas llevan la línea de "ahora" cuando el día es hoy: son
      // recursos del mismo día, no días distintos.
      esHoy,
      encabezado: (
        <div className="grid gap-0.5">
          <span className="truncate text-sm font-medium">{r.name}</span>
          {sucursal && (
            <span className="truncate text-[11px] text-muted-foreground">{sucursal}</span>
          )}
        </div>
      ),
      eventos: turnos.filter((t) => t.resource_id === r.id).map(comoEvento),
    }
  })

  return <RejillaHoraria columnas={columnas} />
}

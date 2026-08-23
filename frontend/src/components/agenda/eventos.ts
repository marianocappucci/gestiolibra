/** Un turno, dicho en el idioma del calendario compartido.
 *
 *  El calendario (`libra-ui/agenda`) sabe dibujar `EventoRejilla`: algo que
 *  empieza, termina, tiene título, color y un lugar a donde ir. Lo que **es**
 *  ese algo lo pone cada producto; acá es un turno.
 *
 *  **El título es el cliente**, no el servicio: en una agenda de turnos lo que
 *  se busca de un vistazo es a quién se atiende. El servicio va de subtítulo
 *  donde entra.
 *
 *  Son tres formas porque el mismo turno dice cosas distintas según dónde se
 *  lo mire, y el lugar disponible también es distinto: en la **semana** los
 *  recursos están mezclados en la columna del día, así que el subtítulo dice de
 *  quién es; en el **día** la columna ya *es* el recurso, así que ese renglón
 *  se libera para el servicio; en el **chip** del mes entra un renglón y medio.
 */
import { claseChip, type EventoRejilla } from 'libra-ui/agenda'
import type { AppointmentStatus } from '../../api'
import type { TurnoConRecurso } from './datos'

/** Un turno cancelado o ausente **no lleva el color de su recurso**.
 *
 *  Sigue en la grilla —sacarlo escondería que ese hueco existió y que alguien
 *  lo reservó— pero apagado y tachado. Con el color del recurso se lee como un
 *  turno vivo, y la columna diría que el box está ocupado a esa hora cuando
 *  está libre: es exactamente la pregunta que la rejilla tiene que contestar
 *  sin abrir nada.
 */
const CLASE_ANULADO = 'bg-muted text-muted-foreground border-border line-through opacity-70'

const ANULADOS: AppointmentStatus[] = ['cancelled', 'no_show']

function clase(t: TurnoConRecurso): string {
  return ANULADOS.includes(t.status) ? CLASE_ANULADO : claseChip(t.recurso_indice)
}

/** Cómo se arma un evento. `hrefTurno` lo pone la pantalla, porque el destino
 *  es la misma pantalla con el turno abierto y eso depende del resto de los
 *  parámetros de la URL. */
export type ArmarEvento = (t: TurnoConRecurso) => EventoRejilla

export function armadores(
  hrefTurno: (id: string) => string,
  nombreCliente: (id: string) => string,
  nombreServicio: (id: string) => string,
): { semana: ArmarEvento; dia: ArmarEvento; chip: ArmarEvento } {
  const base = (t: TurnoConRecurso) => ({
    clave: t.id,
    desde: t.desde,
    hasta: t.hasta,
    titulo: nombreCliente(t.client_id),
    clase: clase(t),
    to: hrefTurno(t.id),
  })
  return {
    semana: (t) => ({ ...base(t), subtitulo: t.recurso_nombre }),
    dia: (t) => ({ ...base(t), subtitulo: nombreServicio(t.service_id) }),
    chip: (t) => ({
      ...base(t),
      subtitulo: [t.recurso_nombre, nombreServicio(t.service_id)].join(' · '),
    }),
  }
}

/** Los turnos de cada día, con la forma que pide la vista de semana o de mes. */
export function porDiaComoEventos(
  porDia: Record<string, TurnoConRecurso[]>,
  como: ArmarEvento,
): Record<string, EventoRejilla[]> {
  return Object.fromEntries(
    Object.entries(porDia).map(([dia, turnos]) => [dia, turnos.map(como)]),
  )
}

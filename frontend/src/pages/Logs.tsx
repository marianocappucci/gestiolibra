// La pantalla vive en libra-ui (v0.12.0), igual que `Usuarios`: nació en
// LibraDesk y se extrajo porque es la misma en los cuatro productos — el
// backend le manda hasta la lista de entidades y los colores.
//
// Sin `basePath`: el default `/logs` es el de este producto.

import { Logs as Compartida } from 'libra-ui/Logs'

/** Sin `icono`: el default del kit es `ICONOS.logDeActividad` (ADR-035), el mismo que el sidebar de este producto. */
export function Logs() {
  return <Compartida />
}

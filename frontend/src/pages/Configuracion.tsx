/** Configuración de Gestiolibra (ítem 5, 2026-08-05).
 *
 *  Hasta ese día este producto **no tenía ninguna pantalla de configuración**:
 *  los datos de la empresa no se podían cargar, el logo no se podía subir, el
 *  SMTP sólo entraba por el backoffice de la suite y el backup era
 *  exclusivamente por CLI.
 *
 *  El armado y las secciones base vienen de `libra-ui/Configuracion`; acá se
 *  declara **lo que corresponde a este producto**. Gestiolibra factura (ARCA)
 *  pero no imprime tickets de mostrador ni usa balanza — ésas son de
 *  VentaLibra.
 *
 *  ## Las tres secciones de la agenda (2026-08-22)
 *
 *  Sucursales, Servicios y Recursos entran acá y no como ítems propios del
 *  sidebar, por pedido del humano: *"la configuración de la facturación por
 *  ARCA debe ir por dentro de configuración y no por fuera"*. El criterio que
 *  esa frase fija es que **lo que se configura vive en un solo lugar**, y estas
 *  tres son exactamente eso — se cargan al arrancar y se tocan poco, a
 *  diferencia de la agenda y los clientes, que se usan todos los días.
 *
 *  Los endpoints existían desde el MVP; lo que faltaba era la pantalla. Sin
 *  ella un cliente nuevo no podía parametrizar nada: ni sus servicios, ni la
 *  duración de cada uno, ni los honorarios, ni la jornada de quien atiende.
 */
import {
  SECCIONES_BASE, SECCION_ARCA, createConfiguracion,
} from 'libra-ui/Configuracion'
import { CalendarClock, MapPin, Scissors, Settings } from 'lucide-react'
import { SucursalesCard } from './configuracion/sucursales'
import { ServiciosCard } from './configuracion/servicios'
import { RecursosCard } from './configuracion/recursos'

export const Configuracion = createConfiguracion({
  // El icono que el sidebar de este producto le da a /configuracion.
  icono: Settings,
  // empresa (+logo), correo (SMTP) y Datos / Backup, más ARCA y la agenda.
  //
  // 🔴 El ORDEN es el del arranque de un cliente nuevo: primero dónde se
  // atiende, después qué se ofrece y quién lo hace. Al revés, un servicio se
  // carga sin poder ponerle precio (el precio es por sucursal) y un recurso sin
  // poder asignarlo.
  secciones: [
    ...SECCIONES_BASE,
    { clave: 'sucursales', label: 'Sucursales', icono: MapPin, contenido: <SucursalesCard /> },
    { clave: 'servicios', label: 'Servicios', icono: Scissors, contenido: <ServiciosCard /> },
    { clave: 'recursos', label: 'Recursos', icono: CalendarClock, contenido: <RecursosCard /> },
    SECCION_ARCA,
  ],
})

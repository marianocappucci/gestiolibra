/** Configuración de Gestiolibra.
 *
 *  El armado y las secciones comunes vienen de `libra-ui/Configuracion`, que
 *  desde la v0.47.0 es **la pantalla de Configuración de la familia entera** —
 *  la de Contalibra, con su barra de pestañas, la sub-navegación de
 *  Integraciones, el botón de *Backup rápido* y los tutoriales. Acá se declara
 *  sólo lo que corresponde a este producto.
 *
 *  🔴 **La copia única vive en el kit, no acá.** Es el punto del pedido del
 *  humano del 2026-08-29: *"si hago una modificación en la configuración o una
 *  actualización se actualice en todas"*. Cualquier arreglo de esta pantalla se
 *  hace en `libra-ui` y llega a los ocho productos.
 *
 *  ## Las tres integraciones, y lo que cambió en cada una
 *
 *  - **MercadoPago** ya tenía sus endpoints montados —el router del motor, con
 *    la bandeja y el webhook— pero **no tenía pestaña**: las credenciales sólo
 *    entraban por el backoffice de la suite. Ahora se cargan desde acá, con el
 *    tutorial de los cuatro datos.
 *  - **ARCA** dejó de pedir un *path del filesystem del servidor* y pasó a
 *    subir el certificado y la clave, validados antes de escribirse. El
 *    `empresa: 'negocio'` no es decorativo: es el slug con el que
 *    `services/billing.py` lee la configuración de facturación, y sin
 *    declararlo una instancia nueva crearía la fila como `default` — donde ese
 *    servicio no mira nunca.
 *  - **Correo (SMTP)** suma el tutorial de la contraseña de aplicación de
 *    Gmail, que este producto no tenía.
 *
 *  ## Las tres secciones de la agenda (2026-08-22)
 *
 *  Sucursales, Servicios y Recursos entran acá y no como ítems propios del
 *  sidebar, por pedido del humano: *"la configuración de la facturación por
 *  ARCA debe ir por dentro de configuración y no por fuera"*. El criterio que
 *  esa frase fija es que **lo que se configura vive en un solo lugar**, y estas
 *  tres son exactamente eso — se cargan al arrancar y se tocan poco, a
 *  diferencia de la agenda y los clientes, que se usan todos los días.
 */
import { createConfiguracion } from 'libra-ui/Configuracion'
import { CalendarClock, MapPin, Scissors, Settings } from 'lucide-react'
import { SucursalesCard } from './configuracion/sucursales'
import { ServiciosCard } from './configuracion/servicios'
import { RecursosCard } from './configuracion/recursos'

export const Configuracion = createConfiguracion({
  // El icono que el sidebar de este producto le da a /configuracion.
  icono: Settings,
  // Sale en el tutorial de Gmail —es el nombre que hay que ponerle a la
  // contraseña de aplicación— y en el de Padrón A13.
  producto: 'Gestiolibra',
  integraciones: {
    mercadopago: true,
    // 🔴 `empresa` es el slug de la fila de `arca_config`, el mismo que usa
    // `services/billing.py`. Ver el docstring de arriba.
    arca: { empresa: 'negocio' },
    email: true,
  },
  // 🔴 El ORDEN es el del arranque de un cliente nuevo: primero dónde se
  // atiende, después qué se ofrece y quién lo hace. Al revés, un servicio se
  // carga sin poder ponerle precio (el precio es por sucursal) y un recurso sin
  // poder asignarlo.
  propias: [
    { clave: 'sucursales', label: 'Sucursales', icono: MapPin, contenido: <SucursalesCard /> },
    { clave: 'servicios', label: 'Servicios', icono: Scissors, contenido: <ServiciosCard /> },
    { clave: 'recursos', label: 'Recursos', icono: CalendarClock, contenido: <RecursosCard /> },
  ],
})

/** Configuración de Gestiolibra (ítem 5, 2026-08-05).
 *
 *  Hasta hoy este producto **no tenía ninguna pantalla de configuración**: los
 *  datos de la empresa no se podían cargar, el logo no se podía subir, el SMTP
 *  sólo entraba por el backoffice de la suite y el backup era exclusivamente
 *  por CLI. El pedido pide las cuatro cosas.
 *
 *  El armado y las secciones vienen de `libra-ui/Configuracion`; acá se declara
 *  **lo que corresponde a este producto**. Gestiolibra factura (ARCA) pero no
 *  imprime tickets de mostrador ni usa balanza — ésas son de VentaLibra.
 */
import {
  SECCIONES_BASE, SECCION_ARCA, createConfiguracion,
} from 'libra-ui/Configuracion'
import { Settings } from 'lucide-react'

export const Configuracion = createConfiguracion({
  // El icono que el sidebar de este producto le da a /configuracion.
  icono: Settings,
  // empresa (+logo), correo (SMTP) y Datos / Backup, más ARCA.
  secciones: [...SECCIONES_BASE, SECCION_ARCA],
})

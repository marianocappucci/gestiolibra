/** La sección «Avisos» de Configuración: cómo salen los recordatorios de turno (ADR-040).
 *
 *  Las dos piezas son del kit (libra-ui ADR-097) y contraparte de `/api/avisos`, que monta el motor (libracore ADR-090):
 *
 *  - `ConfiguracionDeAvisos`: el modo de WhatsApp (apagado, registro o Evolution), su conexión y «probar envío».
 *  - `RegistroDeAvisos`: qué salió y qué no, para contestar «¿le llegó?».
 *
 *  Acá va sólo lo propio de este producto: qué es un `tipo` de aviso (hoy uno, el recordatorio de turno) y si la instancia es una demo.
 *
 *  🔴 **El registro se monta con `esAdmin`.** El teléfono y el mail llegan completos (el registro existe para saber si le llegó a Ana) y
 *  sin esa prop la pieza los enmascara. Es seguro mostrarlos acá: Configuración es de administrador y `/api/avisos/*` también.
 */
import { useEffect, useState } from 'react'
import { ConfiguracionDeAvisos } from 'libra-ui/ConfiguracionDeAvisos'
import { RegistroDeAvisos } from 'libra-ui/RegistroDeAvisos'
import { api } from '../../api'
import { etiquetaDelTipo } from '@/lib/avisos'

/** Si esta instancia es una demo pública: Evolution no se puede conectar y la pantalla lo dice de entrada.
 *
 *  Lo dice `GET /auth/demo` (el mismo que le pregunta el login para mostrar «Entrar a la demo»). Si la consulta falla se asume que no:
 *  el motor igual se niega a guardar Evolution en una demo (422) y la pantalla muestra ese texto. */
function useEsDemo(): boolean {
  const [demo, setDemo] = useState(false)
  useEffect(() => {
    let vivo = true
    api.get<{ enabled?: boolean } | undefined>('/auth/demo')
      .then((r) => { if (vivo) setDemo(Boolean(r?.enabled)) })
      .catch(() => { /* sin dato: se asume que no es una demo */ })
    return () => { vivo = false }
  }, [])
  return demo
}

export function AvisosSeccion() {
  const demo = useEsDemo()
  return (
    <div className="space-y-6">
      <ConfiguracionDeAvisos demo={demo} />
      <RegistroDeAvisos esAdmin etiquetaDelTipo={etiquetaDelTipo} />
    </div>
  )
}

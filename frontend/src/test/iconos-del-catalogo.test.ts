// El menú y los títulos de este producto toman el ícono del catálogo de la familia (libra-ui/iconos-identidad, ADR-035).
//
// 🔴 **Lee los FUENTES, no el DOM**, por lo mismo que `titulos-con-icono.test.ts`: lo que hay que impedir es que un producto vuelva a elegir
// su propio ícono para un concepto del catálogo, y eso no se ve en ningún render. `titulos-con-icono` compara el título con el menú; éste
// compara el menú con el CATÁLOGO, y exige además que los títulos lo digan con `ICONOS.<concepto>` y no con un `lucide` suelto.
//
// Todo el menú de este producto es de conceptos del catálogo: no hay conceptos propios que queden con un ícono de lucide suelto.
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Concepto } from 'libra-ui/iconos-identidad'
import { auditarMenuContraCatalogo, iconoDelTitulo, rutasDelRouter } from 'libra-ui/auditoria-de-titulos'

const SRC = join(process.cwd(), 'src')
const leer = (...partes: string[]) => readFileSync(join(SRC, ...partes), 'utf8')

/** Ruta del menú → concepto del catálogo.  */
const RUTA_A_CONCEPTO: Record<string, Concepto> = {
  '/reportes': 'dashboard',
  '/agenda': 'agenda',
  '/senas': 'senas',
  '/clientes': 'clientes',
  '/usuarios': 'usuarios',
  '/logs': 'logDeActividad',
  '/configuracion': 'configuracion',
}

describe('el menú usa el catálogo de íconos de la familia', () => {
  it('🔴 cada entrada del menú de un concepto del catálogo lleva el ícono del catálogo', () => {
    const { mal, faltan } = auditarMenuContraCatalogo(leer('components', 'Layout.tsx'), RUTA_A_CONCEPTO)
    expect(mal).toEqual([])
    expect(faltan).toEqual([])
  })

  it('🔴 el control — el guard midió todas las rutas del mapa', () => {
    // Sin esto, `mal` y `faltan` vacíos valdrían lo mismo si el parser dejara de encontrar el menú.
    const { medidas } = auditarMenuContraCatalogo(leer('components', 'Layout.tsx'), RUTA_A_CONCEPTO)
    expect(medidas).toBe(Object.keys(RUTA_A_CONCEPTO).length)
  })

  it('🔴 los títulos de pantalla de esos conceptos lo escriben con `ICONOS.<concepto>`', () => {
    // El detalle (`/pacientes/:id`) hereda el concepto de su entrada del menú, como en `auditarTitulos`.
    const rutas = rutasDelRouter(leer('App.tsx'))
    const esperados: string[] = []
    const encontrados: string[] = []
    for (const [ruta, pantalla] of rutas) {
      const concepto = RUTA_A_CONCEPTO[ruta] ?? RUTA_A_CONCEPTO['/' + ruta.replace(/^\/+/, '').split('/')[0]]
      if (!concepto) continue
      const { icono, forma } = iconoDelTitulo(leer('pages', `${pantalla}.tsx`))
      // `Usuarios`, `Logs` y `Configuracion` no escriben el título acá: los rinde el kit con su default del catálogo.
      if (forma === 'sin título') continue
      esperados.push(`${ruta} (${pantalla}): ICONOS.${concepto}`)
      encontrados.push(`${ruta} (${pantalla}): ${icono}`)
    }
    expect(encontrados).toEqual(esperados)
    // El control de este caso: las pantallas con título propio que cubre.
    expect(esperados.length).toBeGreaterThanOrEqual(4)
  })
})

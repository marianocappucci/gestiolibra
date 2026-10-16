// Guard: todo campo donde se elige un cliente ofrece darlo de alta ahí mismo (ADR-071, libra-ui v0.158.0).
//
// 🔴 **Lee los FUENTES, no el DOM**, igual que `selects-buscables.test.ts`: lo que hay que impedir es que vuelva a nacer un desplegable de
// cliente sin alta (el mostrador que no podía elegir un cliente que todavía no estaba cargado), y eso se ve en el JSX. El motor vive en
// `libra-ui/auditoria-de-clientes` y tiene sus propios tests allá.
//
// Un *filtro* que no crea nada se marca con `cliente-sin-alta: <motivo>` en el renglón o en los tres de arriba.
import { describe, expect, it } from 'vitest'
import { join } from 'node:path'
import { auditarCamposDeCliente, describirCamposSinAlta } from 'libra-ui/auditoria-de-clientes'

const SRC = join(process.cwd(), 'src')

describe('todo campo de cliente ofrece el alta', () => {
  const r = auditarCamposDeCliente(SRC)

  it('🔴 el control — el guard midió algo (un parser que devuelve cero sería un falso verde)', () => {
    expect(r.archivos).toBeGreaterThan(0)
    expect(r.campos).toBeGreaterThan(0)
    // El de «Nuevo turno» es de este producto: si deja de contarse, el guard dejó de ver el campo.
    expect(r.conAlta).toBeGreaterThan(0)
  })

  it('🔴 ningún campo de cliente es un desplegable sin alta', () => {
    expect(describirCamposSinAlta(r.infracciones)).toEqual([])
  })
})

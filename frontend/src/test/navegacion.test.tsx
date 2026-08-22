/** El menú y las rutas que el humano pidió mover el 2026-08-22.
 *
 *  Dos pedidos, dos invariantes que sin esto sólo se ven abriendo el navegador:
 *
 *  1. **Dashboard es el primer ítem del sidebar.**
 *  2. **La configuración de ARCA vive dentro de Configuración**, no en una
 *     pantalla suelta. La pantalla suelta (`pages/Facturacion.tsx`) se borró
 *     porque era el mismo formulario contra el mismo `GET/PUT /config/arca`
 *     que `SECCION_ARCA` de libra-ui; la ruta quedó como redirección para que
 *     un favorito viejo no caiga en el catch-all.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

/** El selector de los ítems del menú.
 *
 *  🔴 **No es `role="navigation"`**: el sidebar de shadcn que monta
 *  `libra-ui/Layout` dibuja el menú con `<div>`/`<ul>`, sin ningún `<nav>`, así
 *  que ese rol no existe en la pantalla y la consulta falla con "unable to
 *  find" — pasó al escribir este archivo. `data-sidebar="menu-button"` es el
 *  atributo que el propio primitivo le pone a cada ítem, y sólo a ésos: el
 *  logo, el pie y los links de adentro de una pantalla no lo llevan.
 */
const ITEM_DEL_MENU = 'a[data-sidebar="menu-button"]'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

/** Sesión de admin: es el único rol que ve Dashboard y Configuración. */
function conSesionAdmin() {
  fetchMock.mockImplementation((url: string) => {
    const u = String(url)
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true,
        nombre: 'Ana', modulos: [], empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
    // Sin config cargada. `null` y no `[]`: `[]` es truthy y el formulario de
    // ARCA lo leería como una config con todos los campos en `undefined`,
    // dejando sus inputs sin controlar.
    if (u.includes('/config/')) return Promise.resolve(json(null))
    return Promise.resolve(json([]))
  })
}

function montar(ruta: string) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

/** Los ítems del menú, en orden, una vez montado el shell autenticado. */
async function itemsDelMenu(): Promise<HTMLAnchorElement[]> {
  await waitFor(() =>
    expect(document.querySelectorAll(ITEM_DEL_MENU).length).toBeGreaterThan(0))
  return [...document.querySelectorAll<HTMLAnchorElement>(ITEM_DEL_MENU)]
}

describe('el sidebar', () => {
  it('🔴 Dashboard es el primer ítem', async () => {
    conSesionAdmin()
    montar('/agenda')
    expect((await itemsDelMenu())[0].textContent?.trim()).toBe('Dashboard')
  })

  it('🔴 el control — el menú sigue teniendo el resto de los ítems', async () => {
    // Sin esto, la afirmación de arriba pasaría en verde con un menú de UN
    // solo ítem, que es exactamente la forma en que un reordenamiento mal
    // hecho rompe la pantalla.
    conSesionAdmin()
    montar('/agenda')
    expect((await itemsDelMenu()).map((a) => a.textContent?.trim())).toEqual([
      'Dashboard', 'Agenda', 'Clientes', 'Usuarios', 'Logs', 'Configuración',
    ])
  })

  it('🔴 ya no hay un ítem suelto de Facturación', async () => {
    conSesionAdmin()
    montar('/agenda')
    expect((await itemsDelMenu()).map((a) => a.getAttribute('href')))
      .not.toContain('/facturacion')
  })
})

describe('/facturacion', () => {
  it('🔴 lleva a la sección ARCA de Configuración', async () => {
    conSesionAdmin()
    montar('/facturacion')
    // El título de la card de ARCA, que sólo existe en esa sección: prueba a la
    // vez que la redirección llegó a `/configuracion` y que el `?seccion=arca`
    // eligió la pestaña correcta y no la primera.
    expect(await screen.findByText('Facturación electrónica (ARCA)')).toBeInTheDocument()
  })
})

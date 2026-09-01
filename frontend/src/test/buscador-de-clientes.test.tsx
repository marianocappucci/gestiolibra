// El módulo de clientes no tenía con qué buscar.
//
// La tabla no pagina —`DataTable` no arma row model de paginación—, así que
// con cientos de clientes la única forma de llegar a uno era scrollear. El
// buscador existe en `libra-ui/data-table` desde su v0.8.0: lo que faltaba
// acá era pasarle la prop, y eso es lo que fija este archivo.
//
// ⚠️ Acá las cuatro cosas que se buscan **son columnas** de la tabla, así que
// —a diferencia de Contalibra o VentaLibra— no hay un campo escondido que sirva
// de control de que `campos` no se recortó a lo visible. Lo que sí se controla
// es que cada consulta deje afuera a las demás filas: un buscador que no filtra
// nada pasaría igual si sólo se afirmara que la fila buscada está.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { Clientes } from '../pages/Clientes'

// La pantalla sólo le pregunta al contexto si el usuario es admin (para la
// columna de acciones). Se mockea el shim en vez de montar el `AuthProvider`
// entero: ese trae además el gate de Términos, que pediría su propio endpoint
// y no tiene nada que ver con lo que se está probando.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

const CLIENTES = [
  {
    id: '1', name: 'Panadería del Sol', phone: '2324441122',
    email: 'pedidos@delsol.com.ar', active: true,
    cuit: '30999999995', condicion_iva: 'Responsable Inscripto',
  },
  {
    id: '2', name: 'Ferretería Suárez', phone: '1155667788',
    email: 'ventas@suarez.com.ar', active: true,
    cuit: '20111111112', condicion_iva: 'Monotributista',
  },
  {
    id: '3', name: 'Kiosco 24hs', phone: null,
    email: null, active: true,
    cuit: null, condicion_iva: null,
  },
]

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const cuerpo = String(url).includes('/clients') ? CLIENTES : []
    return Promise.resolve(new Response(JSON.stringify(cuerpo), {
      status: 200, headers: { 'content-type': 'application/json' },
    }))
  }))
})

/** Monta y espera a que la carga inicial termine: antes de eso la tarjeta dice
 *  "Cargando…" y no hay tabla que mirar. */
async function montar() {
  const usuario = userEvent.setup()
  render(<Clientes />)
  await screen.findByText('Panadería del Sol')
  return usuario
}

const buscador = () => screen.getByRole('searchbox', { name: 'Buscar cliente' })

it('filtra la lista por nombre', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), 'kiosco')

  expect(screen.getByText('Kiosco 24hs')).toBeInTheDocument()
  expect(screen.queryByText('Panadería del Sol')).not.toBeInTheDocument()
  expect(screen.queryByText('Ferretería Suárez')).not.toBeInTheDocument()
})

it('filtra por CUIT, que es lo que se tiene del papel', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), '20111111112')

  expect(screen.getByText('Ferretería Suárez')).toBeInTheDocument()
  expect(screen.queryByText('Panadería del Sol')).not.toBeInTheDocument()
})

it('filtra por email', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), 'pedidos@')

  expect(screen.getByText('Panadería del Sol')).toBeInTheDocument()
  expect(screen.queryByText('Ferretería Suárez')).not.toBeInTheDocument()
})

// Los nombres se cargan a mano y con acentos; nadie los teclea al buscar.
it('encuentra sin acentos', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), 'ferreteria suarez')

  expect(screen.getByText('Ferretería Suárez')).toBeInTheDocument()
  expect(screen.queryByText('Kiosco 24hs')).not.toBeInTheDocument()
})

// Buscar y no encontrar no es lo mismo que no tener clientes: el mensaje de
// vacío de la página haría pensar que se perdieron.
it('avisa que no hay resultados, no que no hay clientes', async () => {
  const usuario = await montar()
  await usuario.type(buscador(), 'zzz')

  expect(screen.getByText(/Sin resultados para/)).toBeInTheDocument()
  expect(screen.queryByText('Sin clientes todavía.')).not.toBeInTheDocument()
})

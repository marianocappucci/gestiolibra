/** El equipo del local sin conexión (un nodo de LibraEdge): la agenda de sólo consulta, atender y cobrar, la cola de ARCA y lo que
 *  se dice en pantalla (ADR-036 de este producto, ADR-094 y ADR-095 de libra-ui).
 *
 *  Lo que se ata:
 *  - el cartel «Sin conexión» y el ítem «Cola de comprobantes» salen **sólo en un nodo** (la web queda como siempre);
 *  - en un nodo la agenda no ofrece dar, confirmar, reprogramar ni cancelar turnos; sí «En curso», «No vino» y «Completar»;
 *  - completar sin conexión no da la factura por emitida: avisa que queda en cola y ofrece el comprobante no fiscal;
 *  - las etiquetas «Atendido sin conexión» y «A revisar», y la lista «Turnos a revisar» (que sólo se resuelve en la web);
 *  - un cliente dado de alta en el nodo lleva «Provisorio».
 *
 *  La conexión del nodo es un almacén del kit (`libra-ui/nodo-offline`) que llena quien monta el cartel del layout: acá se llena
 *  consultándolo, y se reinicia entre tests.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { _reiniciarConexionDelNodo, consultarConexionDelNodo } from 'libra-ui/nodo-offline'
import App from '../App'
import { Agenda } from '../pages/Agenda'
import { Clientes } from '../pages/Clientes'
import { AuthProvider } from '../context/AuthContext'

const LUNES = '2026-07-20'
const RUTA_COLA = '/api/nodo/cola?limite=1'

const SUCURSAL = {
  id: 'centro', name: 'Centro', active: true,
  timezone: 'America/Argentina/Buenos_Aires', phone: null, address: null,
}
const RECURSO = { id: 'box-1', name: 'Box 1', branch_id: 'centro', active: true }
const SERVICIO = { id: 'corte', name: 'Corte', duration_minutes: 30, active: true }
const ANA = { id: 'ana', name: 'Ana Gómez', phone: null, email: null, active: true, cuit: null, condicion_iva: null }
const BETO = { id: '-1', name: 'Beto Ruiz', phone: null, email: null, active: true, cuit: null, condicion_iva: null }

const turno = (extra: Record<string, unknown> = {}) => ({
  id: 't1', resource_id: 'box-1', service_id: 'corte', client_id: 'ana',
  starts_at: '2026-07-20T13:00:00Z', ends_at: '2026-07-20T13:30:00Z', status: 'confirmed', ...extra,
})

const CONEXION_DE_UN_NODO = { es_nodo: true, en_linea: false, node_id: 'local-1', cuentas: {}, a_revisar: 0, pedidos: [] }
const FUERA_DE_UN_NODO = { es_nodo: false, en_linea: true, node_id: null, cuentas: {}, a_revisar: 0, pedidos: [] }

let fetchMock: ReturnType<typeof vi.fn>
let pedidos: { url: string; metodo: string; cuerpo: unknown }[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

/** Sirve la API: `extra` pisa por fragmento de URL (el primero que coincide gana). */
function servir(turnos: unknown[], extra: Record<string, unknown> = {}, cola: unknown = CONEXION_DE_UN_NODO) {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const u = String(url)
    pedidos.push({ url: u, metodo: init?.method ?? 'GET', cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
    for (const [fragmento, respuesta] of Object.entries(extra)) {
      if (u.includes(fragmento)) return Promise.resolve(json(respuesta))
    }
    if (u.includes('/api/nodo/cola')) return Promise.resolve(json(cola))
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true, nombre: 'Ana', modulos: [],
        empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
    if (u.includes('/agenda?')) return Promise.resolve(json(turnos))
    if (u.includes('/resources')) return Promise.resolve(json([RECURSO]))
    if (u.includes('/branches')) return Promise.resolve(json([SUCURSAL]))
    if (u.includes('/services')) return Promise.resolve(json([SERVICIO]))
    if (u.includes('/clients')) return Promise.resolve(json([ANA, BETO]))
    if (u.includes('/config/')) return Promise.resolve(json(null))
    return Promise.resolve(json([]))
  })
}

beforeEach(() => {
  _reiniciarConexionDelNodo()
  fetchMock = vi.fn()
  pedidos = []
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => _reiniciarConexionDelNodo())

/** La agenda sola, con la conexión del nodo ya consultada (lo que en la app hace el cartel del layout). */
async function montarAgenda(ruta = `/agenda?dia=${LUNES}`, { esAdmin = true } = {}) {
  const parar = consultarConexionDelNodo({ ruta: RUTA_COLA })
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/agenda" element={<Agenda esAdmin={esAdmin} />} />
        <Route path="/clientes" element={<Clientes />} />
      </Routes>
    </MemoryRouter>,
  )
  // Espera a que la consulta de la cola haya contestado: de ahí sale `esNodo`.
  await waitFor(() => expect(pedidos.some((p) => p.url.includes('/api/nodo/cola'))).toBe(true))
  await new Promise((r) => setTimeout(r, 0))
  return parar
}

function montarApp(ruta: string) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )
}

const ITEM_DEL_MENU = 'a[data-sidebar="menu-button"]'
const itemsDelMenu = () => [...document.querySelectorAll<HTMLAnchorElement>(ITEM_DEL_MENU)].map((a) => a.textContent?.trim())

// ── El layout: el cartel y la cola ────────────────────────────────────────────────────────────────────────────────────

describe('el layout de un nodo', () => {
  it('🔴 sin conexión muestra el cartel y el ítem «Cola de comprobantes»', async () => {
    servir([])
    montarApp('/agenda')
    expect(await screen.findByText(/Sin conexión: la agenda es de consulta/)).toBeInTheDocument()
    await waitFor(() => expect(itemsDelMenu()).toContain('Cola de comprobantes'))
  })

  it('🔴 el cartel no habla de cartas de porte ni de CPE: eso es de LibraCargo', async () => {
    servir([])
    montarApp('/agenda')
    const cartel = await screen.findByText(/Sin conexión: la agenda es de consulta/)
    expect(cartel.textContent).not.toMatch(/CPE|carta/i)
  })

  it('🔴 el control — fuera de un nodo no hay cartel ni «Cola de comprobantes»', async () => {
    servir([], {}, FUERA_DE_UN_NODO)
    montarApp('/agenda')
    await waitFor(() => expect(itemsDelMenu().length).toBeGreaterThan(0))
    await waitFor(() => expect(pedidos.some((p) => p.url.includes('/api/nodo/cola'))).toBe(true))
    expect(itemsDelMenu()).not.toContain('Cola de comprobantes')
    expect(screen.queryByText(/Sin conexión/)).not.toBeInTheDocument()
  })
})

describe('/cola', () => {
  it('muestra la factura pedida sin conexión, nombrada por lo que se cobró y no por el uuid del turno', async () => {
    const pedido = {
      id: 1, origen_producto: 'gestiolibra', origen_instancia: 'local-1', origen_tipo: 'documento',
      origen_id: '27f03261-a893-4054-89ef-d05b35d90b94', estado: 'esperando', fecha_ref: '2026-10-25', concepto: 1,
      intentos: 0, ultimo_error: '', resultado: null, revision: 0, created_at: '2026-10-25T10:00:00Z',
      updated_at: '2026-10-25T10:00:00Z', resuelto_at: '',
      datos: { servicio: 'Corte', cliente: { nombre: 'Ana Gómez' }, precio: '1000.00' },
    }
    servir([], {}, { ...CONEXION_DE_UN_NODO, cuentas: { esperando: 1 }, pedidos: [pedido] })
    montarApp('/cola')
    expect(await screen.findByText('Factura · Corte · Ana Gómez')).toBeInTheDocument()
    expect(screen.queryByText(/27f03261/)).not.toBeInTheDocument()
  })

  it('fuera de un nodo la pantalla lo dice y no rompe', async () => {
    servir([], {}, FUERA_DE_UN_NODO)
    montarApp('/cola')
    expect(await screen.findByText(/no es un nodo/i)).toBeInTheDocument()
  })
})

// ── La agenda ─────────────────────────────────────────────────────────────────────────────────────────────────────────

describe('la agenda de un nodo', () => {
  it('🔴 es de sólo consulta: no hay «Nuevo turno» ni confirmar, reprogramar o cancelar', async () => {
    servir([turno({ status: 'confirmed' })])
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    const dialogo = await screen.findByRole('dialog')
    expect(screen.queryByRole('button', { name: /Nuevo turno/, hidden: true })).not.toBeInTheDocument()
    for (const nombre of ['Confirmar', 'Reprogramar', 'Cancelar turno']) {
      expect(within(dialogo).queryByRole('button', { name: nombre })).not.toBeInTheDocument()
    }
    parar()
  })

  it('🔴 se puede atender: «En curso», «No vino» y «Completar»', async () => {
    servir([turno({ status: 'confirmed' })])
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    const dialogo = await screen.findByRole('dialog')
    for (const nombre of ['En curso', 'No vino', 'Completar']) {
      expect(within(dialogo).getByRole('button', { name: nombre })).toBeInTheDocument()
    }
    await userEvent.click(within(dialogo).getByRole('button', { name: 'En curso' }))
    await waitFor(() => expect(
      pedidos.some((p) => p.url === '/appointments/t1/start' && p.metodo === 'POST')).toBe(true))
    parar()
  })

  it('«No vino» llama a su ruta', async () => {
    servir([turno({ status: 'confirmed' })])
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'No vino' }))
    await waitFor(() => expect(
      pedidos.some((p) => p.url === '/appointments/t1/no-show' && p.metodo === 'POST')).toBe(true))
    parar()
  })

  it('un turno en curso se puede completar', async () => {
    servir([turno({ status: 'in_progress' })])
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByRole('button', { name: 'Completar' })).toBeInTheDocument()
    expect(within(dialogo).queryByRole('button', { name: 'En curso' })).not.toBeInTheDocument()
    parar()
  })

  it('🔴 completar sin conexión no da la factura por emitida: avisa que queda en cola y ofrece el comprobante no fiscal', async () => {
    servir([turno({ status: 'confirmed' })], {
      '/appointments/t1/complete': {
        id: 't1', status: 'completed', factura: null, atendido_sin_conexion: true, en_cola: true, estado: 'esperando',
        pedido_id: 1, mensaje: 'Sin conexión: la factura queda en la cola.', motivo: '',
        comprobante_no_fiscal: '/appointments/t1/comprobante-no-fiscal',
      },
    })
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Completar' }))

    const aviso = await screen.findByRole('dialog', { name: 'Turno cobrado sin conexión' })
    expect(within(aviso).getByText('Se emite al volver la conexión.')).toBeInTheDocument()
    expect(within(aviso).getByRole('link', { name: /Comprobante no fiscal/ })).toHaveAttribute(
      'href', '/appointments/t1/comprobante-no-fiscal')
    expect(screen.queryByText('Factura emitida')).not.toBeInTheDocument()
    parar()
  })

  it('el control — con conexión la factura sale en el acto y se muestra la de siempre', async () => {
    servir([turno({ status: 'confirmed' })], {
      '/appointments/t1/complete': {
        id: 't1', status: 'completed', atendido_sin_conexion: true, comprobante_no_fiscal: null,
        factura: { id: 1, tipo: 6, punto_venta: 3, numero: 1, fecha: '2026-10-25', cliente_cuit: '', cliente_razon: 'Ana',
                   total: 1000, cae: '75123456789012', cae_vto: '20261231' },
      },
    })
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Completar' }))
    expect(await screen.findByText('Factura emitida')).toBeInTheDocument()
    expect(screen.queryByText('Turno cobrado sin conexión')).not.toBeInTheDocument()
    parar()
  })

  it('la seña se ve pero no se pide ni se cobra: es de la web', async () => {
    servir([turno({ status: 'confirmed' })], {
      '/appointments/t1/deposit': { id: 's1', appointment_id: 't1', amount: '400.00', status: 'pending', medio_pago: null },
    })
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    const dialogo = await screen.findByRole('dialog')
    expect(await within(dialogo).findByText('La seña se pide y se cobra desde la web.')).toBeInTheDocument()
    expect(within(dialogo).queryByRole('button', { name: 'Cobrar seña' })).not.toBeInTheDocument()
    expect(within(dialogo).queryByRole('button', { name: 'Pedir seña' })).not.toBeInTheDocument()
    parar()
  })
})

describe('la agenda de la web', () => {
  it('🔴 el control — sigue como siempre: nuevo turno, confirmar, reprogramar y cancelar; nada de «En curso» ni «No vino»', async () => {
    servir([turno({ status: 'pending' })], {}, FUERA_DE_UN_NODO)
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    const dialogo = await screen.findByRole('dialog')
    // `hidden`: con el diálogo abierto el resto de la pantalla queda `aria-hidden`.
    expect(screen.getByRole('button', { name: /Nuevo turno/, hidden: true })).toBeInTheDocument()
    for (const nombre of ['Confirmar', 'Reprogramar', 'Cancelar turno']) {
      expect(within(dialogo).getByRole('button', { name: nombre })).toBeInTheDocument()
    }
    for (const nombre of ['En curso', 'No vino']) {
      expect(within(dialogo).queryByRole('button', { name: nombre })).not.toBeInTheDocument()
    }
    parar()
  })
})

// ── Las etiquetas y la lista «a revisar» ──────────────────────────────────────────────────────────────────────────────

describe('las etiquetas del turno', () => {
  it('un turno atendido en esta PC y todavía sin subir dice «Atendido sin conexión»', async () => {
    servir([turno({ status: 'completed', atendido_sin_conexion: true })])
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Atendido sin conexión')).toBeInTheDocument()
    expect(within(dialogo).queryByText('A revisar')).not.toBeInTheDocument()
    parar()
  })

  it('uno que subió y en la web cambió dice «A revisar», nunca las dos', async () => {
    servir([turno({ status: 'cancelled', atendido_sin_conexion: true, a_revisar: true, motivo: 'cancelado' })])
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('A revisar')).toBeInTheDocument()
    expect(within(dialogo).queryByText('Atendido sin conexión')).not.toBeInTheDocument()
    parar()
  })

  it('el control — un turno común no lleva ninguna', async () => {
    servir([turno()])
    const parar = await montarAgenda(`/agenda?dia=${LUNES}&turno=t1`)
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).queryByText('Atendido sin conexión')).not.toBeInTheDocument()
    expect(within(dialogo).queryByText('A revisar')).not.toBeInTheDocument()
    parar()
  })
})

describe('Turnos a revisar', () => {
  const fila = {
    atencion_id: 'a'.repeat(36), appointment_id: 't1', estado: 'completed', at: '2026-10-25T10:40:00-03:00', actor: 'Ana',
    motivo: 'cancelado', estado_despues: 'cancelled', resultado: 'a_revisar', revisada_at: null,
    cliente: 'Ana Gómez', servicio: 'Corte', starts_at: '2026-07-20T13:00:00+00:00',
  }

  it('🔴 en la web aparece la lista, con el turno nombrado, y «Ya lo revisé» lo saca', async () => {
    servir([turno()], { '/api/nodo/turnos-a-revisar/revisar': [], '/api/nodo/turnos-a-revisar': [fila] }, FUERA_DE_UN_NODO)
    const parar = await montarAgenda()
    const panel = await screen.findByRole('region', { name: /Turnos a revisar/ })
    expect(within(panel).getByText('Ana Gómez · Corte — 20-07-2026')).toBeInTheDocument()
    expect(within(panel).getByText('Se canceló en la web.')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: 'Ya lo revisé' }))
    await waitFor(() => expect(pedidos.some((p) => p.url === '/api/nodo/turnos-a-revisar/revisar' && p.metodo === 'POST'
      && JSON.stringify(p.cuerpo) === JSON.stringify({ atenciones: ['a'.repeat(36)] }))).toBe(true))
    parar()
  })

  it('en la PC del local la lista se ve pero la revisión es de la web: sin botón', async () => {
    servir([turno()], { '/api/nodo/turnos-a-revisar': [fila] })
    const parar = await montarAgenda()
    const panel = await screen.findByRole('region', { name: /Turnos a revisar/ })
    expect(within(panel).queryByRole('button', { name: 'Ya lo revisé' })).not.toBeInTheDocument()
    parar()
  })

  it('el control — sin turnos a revisar no hay panel', async () => {
    servir([turno()], {}, FUERA_DE_UN_NODO)
    const parar = await montarAgenda()
    await waitFor(() => expect(pedidos.some((p) => p.url === '/api/nodo/turnos-a-revisar')).toBe(true))
    expect(screen.queryByRole('region', { name: /Turnos a revisar/ })).not.toBeInTheDocument()
    parar()
  })
})

// ── Los clientes ──────────────────────────────────────────────────────────────────────────────────────────────────────

describe('los clientes de un nodo', () => {
  function montarClientes() {
    render(
      <MemoryRouter initialEntries={['/clientes']}>
        <AuthProvider><App /></AuthProvider>
      </MemoryRouter>,
    )
  }

  it('🔴 el que se dio de alta sin conexión lleva «Provisorio» y el de siempre no', async () => {
    servir([])
    montarClientes()
    const beto = (await screen.findByText('Beto Ruiz')).closest('tr') as HTMLElement
    expect(within(beto).getByText('Provisorio')).toBeInTheDocument()
    const ana = (await screen.findByText('Ana Gómez')).closest('tr') as HTMLElement
    expect(within(ana).queryByText('Provisorio')).not.toBeInTheDocument()
  })

  it('en un nodo no se ofrece editar ni borrar (409 del backend): sólo el alta', async () => {
    servir([])
    montarClientes()
    await screen.findByText('Beto Ruiz')
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Editar cliente' })).not.toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Eliminar cliente' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Nuevo cliente/ })).toBeInTheDocument()
  })

  it('el control — en la web se edita y se borra', async () => {
    servir([], {}, FUERA_DE_UN_NODO)
    montarClientes()
    await screen.findByText('Ana Gómez')
    expect((await screen.findAllByRole('button', { name: 'Editar cliente' })).length).toBeGreaterThan(0)
  })
})

// Reprogramar un turno y su seña, desde el detalle del turno en la agenda.
//
// Los dos endpoints existían desde el MVP (`/appointments/{id}/reschedule` y
// `/appointments/{id}/deposit`) y no tenían pantalla hasta el 2026-09-11.
//
// 🔴 **Lo que más se mide es el CABLE**, no el dibujo: qué se manda y a dónde.
// Reprogramar manda la hora de pared SIN huso, igual que el alta — el backend
// la interpreta con la zona de la sucursal —, y el monto de la seña sale con
// punto aunque se escriba con coma, que es como se escribe acá.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Agenda } from '../pages/Agenda'

const LUNES = '2026-07-20'

const SUCURSAL = {
  id: 'centro', name: 'Centro', active: true,
  timezone: 'America/Argentina/Buenos_Aires', phone: null, address: null,
}
const RECURSO = { id: 'box-1', name: 'Box 1', branch_id: 'centro', active: true }
const SERVICIO = { id: 'corte', name: 'Corte', duration_minutes: 30, active: true }
const CLIENTE = {
  id: 'ana', name: 'Ana Gómez', phone: null, email: null, active: true,
  cuit: null, condicion_iva: null,
}
const MEDIOS = [{ id: 'efectivo', label: 'Efectivo' }, { id: 'transferencia', label: 'Transferencia' }]

/** Las 10:00 del lunes en la sucursal (UTC-3).
 *
 *  Confirmado y no pendiente a propósito: el badge de un turno pendiente dice
 *  "Pendiente", igual que el de una seña pendiente, y buscar la seña por su
 *  estado encontraría las dos. */
const TURNO = {
  id: 't-1', resource_id: 'box-1', service_id: 'corte', client_id: 'ana',
  starts_at: '2026-07-20T13:00:00Z', ends_at: '2026-07-20T13:30:00Z',
  status: 'confirmed',
}

const SENA_PENDIENTE = {
  id: 'd-1', appointment_id: 't-1', amount: '1500.00', status: 'pending', medio_pago: null,
}

type Respuesta = { status?: number; body: unknown }
type Pedido = { url: string; metodo: string; cuerpo: unknown }

let fetchMock: ReturnType<typeof vi.fn>
let pedidos: Pedido[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

/** Sirve el catálogo y la agenda; `rutas` pisa lo que haga falta por
 *  `"METODO url"` exacto (sin query), con su código. */
function servir({
  turno = TURNO as Record<string, unknown>,
  rutas = {} as Record<string, Respuesta | ((p: Pedido) => Respuesta)>,
} = {}) {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const u = String(url)
    const pedido = {
      url: u,
      metodo: init?.method ?? 'GET',
      cuerpo: init?.body ? JSON.parse(String(init.body)) : null,
    }
    pedidos.push(pedido)
    const propia = rutas[`${pedido.metodo} ${u.split('?')[0]}`]
    if (propia) {
      const r = typeof propia === 'function' ? propia(pedido) : propia
      return Promise.resolve(json(r.body, r.status ?? 200))
    }
    if (u.includes('/agenda?')) return Promise.resolve(json([turno]))
    if (u.includes('/deposit')) return Promise.resolve(json({ detail: 'deposit not found' }, 404))
    if (u.includes('/resources')) return Promise.resolve(json([RECURSO]))
    if (u.includes('/branches')) return Promise.resolve(json([SUCURSAL]))
    if (u.includes('/services')) return Promise.resolve(json([SERVICIO]))
    if (u.includes('/clients')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/medios-pago')) return Promise.resolve(json(MEDIOS))
    return Promise.resolve(json({}))
  })
}

let urlActual = ''
function EspiaDeUrl() {
  const location = useLocation()
  urlActual = `${location.pathname}${location.search}`
  return null
}

function montar({ esAdmin = true } = {}) {
  return render(
    <MemoryRouter initialEntries={[`/agenda?dia=${LUNES}&turno=t-1`]}>
      <EspiaDeUrl />
      <Routes>
        <Route path="/agenda" element={<Agenda esAdmin={esAdmin} />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  fetchMock = vi.fn()
  pedidos = []
  urlActual = ''
  vi.stubGlobal('fetch', fetchMock)
})

async function detalleDelTurno() {
  return screen.findByRole('dialog', { name: 'Ana Gómez' })
}

async function abrirReprogramar() {
  const detalle = await detalleDelTurno()
  await userEvent.click(within(detalle).getByRole('button', { name: 'Reprogramar' }))
  return screen.findByRole('dialog', { name: 'Reprogramar turno' })
}

describe('reprogramar un turno', () => {
  it('🔴 manda la hora nueva sin huso y el motivo, y va al día nuevo', async () => {
    servir({ rutas: { 'POST /appointments/t-1/reschedule': { body: { id: 't-1' } } } })
    montar()
    const dialogo = await abrirReprogramar()

    // Prellenado con la hora actual en la hora de pared de la SUCURSAL: 10:00,
    // no las 13:00 del instante UTC.
    const horario = within(dialogo).getByLabelText(/^Horario nuevo/) as HTMLInputElement
    expect(horario.value).toBe('2026-07-20T10:00')
    // Y la hora actual a la vista, en el formato del ecosistema.
    expect(within(dialogo).getByText(/20-07-2026 10:00/)).toBeInTheDocument()

    // 🔴 `fireEvent.change` y no `userEvent.type`: tipear en un
    // `datetime-local` de jsdom es un render por tecla, y con la suite entera
    // en paralelo este test se pasaba de los 5 s — y el de abajo no llegaba a
    // ver el POST dentro del `waitFor`. Lo que se prueba es qué se manda, no
    // el teclado.
    fireEvent.change(horario, { target: { value: '2026-07-22T11:30' } })
    await userEvent.type(within(dialogo).getByLabelText('Motivo (opcional)'), 'Otro día')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Reprogramar' }))

    await waitFor(() => {
      const movido = pedidos.find((p) => p.url === '/appointments/t-1/reschedule')
      expect(movido?.metodo).toBe('POST')
      expect(movido?.cuerpo).toEqual({ starts_at: '2026-07-22T11:30', reason: 'Otro día' })
    })
    // Se cierra el turno y la agenda se para en el día nuevo.
    await waitFor(() => expect(urlActual).toContain('dia=2026-07-22'))
    expect(urlActual).not.toContain('turno=')
  })

  it('sin motivo no manda `reason`: el motor conservaría el anterior', async () => {
    servir({ rutas: { 'POST /appointments/t-1/reschedule': { body: { id: 't-1' } } } })
    montar()
    const dialogo = await abrirReprogramar()
    const horario = within(dialogo).getByLabelText(/^Horario nuevo/)
    fireEvent.change(horario, { target: { value: '2026-07-20T12:00' } })
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Reprogramar' }))
    await waitFor(() => expect(
      pedidos.find((p) => p.url === '/appointments/t-1/reschedule')?.cuerpo,
    ).toEqual({ starts_at: '2026-07-20T12:00' }))
  })

  it('🔴 si el backend lo rechaza, muestra su motivo y el diálogo queda abierto', async () => {
    const motivo = 'Ese horario ya está ocupado. Elegí otro o revisá la agenda del recurso.'
    servir({ rutas: { 'POST /appointments/t-1/reschedule': { status: 409, body: { detail: motivo } } } })
    montar()
    const dialogo = await abrirReprogramar()
    const horario = within(dialogo).getByLabelText(/^Horario nuevo/)
    fireEvent.change(horario, { target: { value: '2026-07-20T14:00' } })
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Reprogramar' }))

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent(motivo)
    expect(screen.getByRole('dialog', { name: 'Reprogramar turno' })).toBeInTheDocument()
    expect(urlActual).toContain('turno=t-1')
  })

  it('no manda nada si el horario es el mismo que ya tiene', async () => {
    servir()
    montar()
    const dialogo = await abrirReprogramar()
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Reprogramar' }))
    expect(await within(dialogo).findByText('Es el mismo horario que ya tiene')).toBeInTheDocument()
    expect(pedidos.some((p) => p.url.endsWith('/reschedule'))).toBe(false)
  })

  it('🔴 un turno completado no ofrece reprogramar', async () => {
    servir({ turno: { ...TURNO, status: 'completed' } })
    montar()
    const detalle = await detalleDelTurno()
    expect(within(detalle).queryByRole('button', { name: 'Reprogramar' })).not.toBeInTheDocument()
  })

  it('🔴 el control — uno pendiente sí', async () => {
    servir({ turno: { ...TURNO, status: 'pending' } })
    montar()
    const detalle = await detalleDelTurno()
    expect(within(detalle).getByRole('button', { name: 'Reprogramar' })).toBeInTheDocument()
  })
})

describe('la seña del turno', () => {
  it('🔴 sin seña, se pide con el monto escrito con coma y sale con punto', async () => {
    servir({ rutas: { 'POST /appointments/t-1/deposit': { status: 201, body: SENA_PENDIENTE } } })
    montar()
    const detalle = await detalleDelTurno()
    expect(await within(detalle).findByText('Sin seña')).toBeInTheDocument()

    await userEvent.type(within(detalle).getByLabelText('Monto de la seña'), '1500,50')
    await userEvent.click(within(detalle).getByRole('button', { name: 'Pedir seña' }))

    await waitFor(() => {
      const pedido = pedidos.find((p) => p.metodo === 'POST' && p.url === '/appointments/t-1/deposit')
      expect(pedido?.cuerpo).toEqual({ amount: '1500.50' })
    })
  })

  it('un monto en cero no se manda', async () => {
    servir()
    montar()
    const detalle = await detalleDelTurno()
    await within(detalle).findByText('Sin seña')
    await userEvent.type(within(detalle).getByLabelText('Monto de la seña'), '0')
    await userEvent.click(within(detalle).getByRole('button', { name: 'Pedir seña' }))
    expect(await within(detalle).findByText('Tiene que ser un monto mayor a cero')).toBeInTheDocument()
    expect(pedidos.some((p) => p.metodo === 'POST' && p.url.endsWith('/deposit'))).toBe(false)
  })

  it('🔴 una seña pendiente se cobra con su medio de pago', async () => {
    servir({
      rutas: {
        'GET /appointments/t-1/deposit': { body: SENA_PENDIENTE },
        'POST /deposits/d-1/mark-paid': { body: { ...SENA_PENDIENTE, status: 'paid' } },
      },
    })
    montar()
    const detalle = await detalleDelTurno()
    expect(await within(detalle).findByText('Pendiente')).toBeInTheDocument()
    expect(within(detalle).getByText(/1\.500,00/)).toBeInTheDocument()

    await userEvent.click(within(detalle).getByRole('button', { name: 'Cobrar seña' }))
    const cobro = await screen.findByRole('dialog', { name: 'Cobrar seña' })
    // El select tiene nombre accesible: se lo encuentra por su rótulo.
    await userEvent.click(within(cobro).getByRole('combobox', { name: 'Medio de pago' }))
    await userEvent.click(await screen.findByRole('option', { name: 'Transferencia' }))
    await userEvent.click(within(cobro).getByRole('button', { name: 'Registrar cobro' }))

    await waitFor(() => expect(
      pedidos.find((p) => p.url === '/deposits/d-1/mark-paid')?.cuerpo,
    ).toEqual({ medio_pago: 'transferencia' }))
  })

  it('🔴 el staff ve la seña pero no la puede cobrar', async () => {
    servir({ rutas: { 'GET /appointments/t-1/deposit': { body: SENA_PENDIENTE } } })
    montar({ esAdmin: false })
    const detalle = await detalleDelTurno()
    expect(await within(detalle).findByText('Pendiente')).toBeInTheDocument()
    expect(within(detalle).queryByRole('button', { name: 'Cobrar seña' })).not.toBeInTheDocument()
    expect(within(detalle).getByText(/lo registra un administrador/)).toBeInTheDocument()
  })

  it('una seña cobrada se devuelve, confirmando antes', async () => {
    servir({
      rutas: {
        'GET /appointments/t-1/deposit': {
          body: { ...SENA_PENDIENTE, status: 'paid', medio_pago: 'efectivo' },
        },
        'POST /deposits/d-1/refund': { body: { ...SENA_PENDIENTE, status: 'refunded' } },
      },
    })
    montar()
    const detalle = await detalleDelTurno()
    expect(await within(detalle).findByText('Cobrada')).toBeInTheDocument()
    // El medio se muestra con su nombre, no con su id.
    expect(within(detalle).getByText('Efectivo')).toBeInTheDocument()

    await userEvent.click(within(detalle).getByRole('button', { name: 'Devolver seña' }))
    const confirmar = await screen.findByRole('alertdialog')
    expect(pedidos.some((p) => p.url.endsWith('/refund'))).toBe(false)
    await userEvent.click(within(confirmar).getByRole('button', { name: 'Devolver' }))
    await waitFor(() => expect(
      pedidos.some((p) => p.metodo === 'POST' && p.url === '/deposits/d-1/refund'),
    ).toBe(true))
  })

  it('🔴 sin el módulo de señas (403), la sección no aparece', async () => {
    servir({
      rutas: { 'GET /appointments/t-1/deposit': { status: 403, body: { detail: 'Módulo no habilitado' } } },
    })
    montar()
    const detalle = await detalleDelTurno()
    await waitFor(() => expect(
      pedidos.some((p) => p.url === '/appointments/t-1/deposit'),
    ).toBe(true))
    await waitFor(() => expect(within(detalle).queryByText('Cargando…')).not.toBeInTheDocument())
    expect(within(detalle).queryByRole('region', { name: 'Seña' })).not.toBeInTheDocument()
    expect(within(detalle).queryByText('Sin seña')).not.toBeInTheDocument()
  })
})

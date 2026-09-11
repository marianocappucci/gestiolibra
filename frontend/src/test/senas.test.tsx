// La pantalla de Señas y el contador del Dashboard que lleva a ella.
//
// 🔴 **El día y la hora del turno son los de la sucursal**, igual que en la
// agenda: la API manda instantes en UTC, y un turno de las 21:30 del lunes en
// Buenos Aires es `...T00:30:00Z` del martes. La lista tiene que decir lunes.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Senas } from '../pages/Senas'
import { Dashboard } from '../pages/Dashboard'

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

/** Seña pendiente de un turno de las 21:30 del lunes 20 (en UTC, martes 00:30). */
const PENDIENTE = {
  id: 'd-1', appointment_id: 't-1', amount: '1000.00', status: 'pending', medio_pago: null,
  appointment_starts_at: '2026-07-21T00:30:00Z', appointment_status: 'confirmed',
  client_id: 'ana', service_id: 'corte', resource_id: 'box-1',
}
const COBRADA = {
  ...PENDIENTE, id: 'd-2', appointment_id: 't-2', amount: '2500.50', status: 'paid',
  medio_pago: 'efectivo', appointment_starts_at: '2026-07-22T13:00:00Z',
}

type Pedido = { url: string; metodo: string; cuerpo: unknown }
let fetchMock: ReturnType<typeof vi.fn>
let pedidos: Pedido[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

function servir(senas: unknown[] | { status: number; body: unknown }) {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    pedidos.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
    if (metodo === 'POST') return Promise.resolve(json({}))
    if (u.startsWith('/deposits')) {
      if (!Array.isArray(senas)) return Promise.resolve(json(senas.body, senas.status))
      const estado = new URL(u, 'http://x').searchParams.get('status')
      return Promise.resolve(json(estado
        ? senas.filter((s) => (s as { status: string }).status === estado) : senas))
    }
    if (u.includes('/resources')) return Promise.resolve(json([RECURSO]))
    if (u.includes('/branches')) return Promise.resolve(json([SUCURSAL]))
    if (u.includes('/services')) return Promise.resolve(json([SERVICIO]))
    if (u.includes('/clients')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/medios-pago')) return Promise.resolve(json(MEDIOS))
    return Promise.resolve(json([]))
  })
}

let urlActual = ''
function EspiaDeUrl() {
  const location = useLocation()
  urlActual = `${location.pathname}${location.search}`
  return null
}

function montar(ruta = '/senas') {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <EspiaDeUrl />
      <Routes>
        <Route path="/senas" element={<Senas />} />
        <Route path="/reportes" element={<Dashboard />} />
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

/** La fila de la tabla que contiene un texto. */
async function fila(texto: string | RegExp): Promise<HTMLElement> {
  return (await screen.findByText(texto)).closest('tr') as HTMLElement
}

describe('la lista de señas', () => {
  it('🔴 abre en las pendientes y las pide filtradas al backend', async () => {
    servir([PENDIENTE, COBRADA])
    montar()
    expect(await screen.findByText('Ana Gómez')).toBeInTheDocument()
    expect(pedidos.some((p) => p.url === '/deposits?status=pending')).toBe(true)
    // La cobrada no está: la pantalla muestra lo que pidió, no todo.
    expect(screen.queryByText(/2\.500,50/)).not.toBeInTheDocument()
  })

  it('🔴 el turno se muestra con el día y la hora de la SUCURSAL, dd-mm-aaaa', async () => {
    servir([PENDIENTE])
    montar()
    const renglon = await fila('Ana Gómez')
    // 21:30 del lunes 20, no 00:30 del martes 21.
    expect(within(renglon).getByText('20-07-2026 21:30')).toBeInTheDocument()
    expect(within(renglon).getByText(/1\.000,00/)).toBeInTheDocument()
    expect(within(renglon).getByText('Pendiente')).toBeInTheDocument()
    expect(within(renglon).getByText('Corte')).toBeInTheDocument()
  })

  it('🔴 el turno lleva a la agenda, parado en su día', async () => {
    servir([PENDIENTE])
    montar()
    const renglon = await fila('Ana Gómez')
    expect(within(renglon).getByRole('link', { name: '20-07-2026 21:30' }))
      .toHaveAttribute('href', '/agenda?dia=2026-07-20&turno=t-1')
  })

  it('la pestaña de cobradas cambia la URL y lo que se pide', async () => {
    servir([PENDIENTE, COBRADA])
    montar()
    await screen.findByText('Ana Gómez')
    await userEvent.click(screen.getByRole('tab', { name: 'Cobradas' }))
    await waitFor(() => expect(urlActual).toBe('/senas?estado=paid'))
    const renglon = await fila(/2\.500,50/)
    expect(pedidos.some((p) => p.url === '/deposits?status=paid')).toBe(true)
    expect(within(renglon).getByText('Cobrada')).toBeInTheDocument()
    // El medio con su nombre, no con su id.
    expect(within(renglon).getByText('Efectivo')).toBeInTheDocument()
  })

  it('"Todas" no filtra', async () => {
    servir([PENDIENTE, COBRADA])
    montar('/senas?estado=todas')
    await screen.findByText(/2\.500,50/)
    expect(pedidos.some((p) => p.url === '/deposits')).toBe(true)
    expect(screen.getByText(/1\.000,00/, { selector: 'div' })).toBeInTheDocument()
  })

  it('suma lo que queda por cobrar', async () => {
    servir([PENDIENTE, { ...PENDIENTE, id: 'd-3', amount: '500.25' }])
    montar()
    await screen.findAllByText('Ana Gómez')
    expect(screen.getByText(/Pendiente de cobro/)).toHaveTextContent(/1\.500,25/)
  })

  it('🔴 cobrar pide el medio de pago y lo manda', async () => {
    servir([PENDIENTE])
    montar()
    const renglon = await fila('Ana Gómez')
    await userEvent.click(within(renglon).getByRole('button', { name: 'Cobrar la seña de Ana Gómez' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Cobrar seña' })

    // Sin medio no se manda nada: el cobro entraría a la caja con el medio
    // en blanco.
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Registrar cobro' }))
    expect(await within(dialogo).findByText('Elegí cómo se cobró')).toBeInTheDocument()
    expect(pedidos.some((p) => p.url.endsWith('/mark-paid'))).toBe(false)

    await userEvent.click(within(dialogo).getByRole('combobox', { name: 'Medio de pago' }))
    await userEvent.click(await screen.findByRole('option', { name: 'Efectivo' }))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Registrar cobro' }))
    await waitFor(() => {
      const cobro = pedidos.find((p) => p.url === '/deposits/d-1/mark-paid')
      expect(cobro?.metodo).toBe('POST')
      expect(cobro?.cuerpo).toEqual({ medio_pago: 'efectivo' })
    })
  })

  it('🔴 devolver una cobrada pide confirmación y manda el refund', async () => {
    servir([COBRADA])
    montar('/senas?estado=paid')
    const renglon = await fila(/2\.500,50/)
    await userEvent.click(within(renglon).getByRole('button', { name: 'Devolver la seña de Ana Gómez' }))
    const confirmar = await screen.findByRole('alertdialog')
    expect(pedidos.some((p) => p.url.endsWith('/refund'))).toBe(false)
    await userEvent.click(within(confirmar).getByRole('button', { name: 'Devolver' }))
    await waitFor(() => expect(
      pedidos.some((p) => p.metodo === 'POST' && p.url === '/deposits/d-2/refund'),
    ).toBe(true))
  })

  it('una pendiente se puede marcar fallida', async () => {
    servir([PENDIENTE])
    montar()
    const renglon = await fila('Ana Gómez')
    await userEvent.click(within(renglon).getByRole('button', { name: 'Marcar fallida la seña de Ana Gómez' }))
    const confirmar = await screen.findByRole('alertdialog')
    await userEvent.click(within(confirmar).getByRole('button', { name: 'Marcar fallida' }))
    await waitFor(() => expect(
      pedidos.some((p) => p.metodo === 'POST' && p.url === '/deposits/d-1/mark-failed'),
    ).toBe(true))
  })

  it('una cobrada no ofrece cobrar de nuevo', async () => {
    servir([COBRADA])
    montar('/senas?estado=paid')
    const renglon = await fila(/2\.500,50/)
    expect(within(renglon).queryByRole('button', { name: /Cobrar/ })).not.toBeInTheDocument()
  })

  it('sin permiso (403) lo dice en vez de mostrar una tabla vacía', async () => {
    servir({ status: 403, body: { detail: 'Forbidden' } })
    montar()
    expect(await screen.findByText(/No tenés acceso a las señas/)).toBeInTheDocument()
  })
})

describe('el Dashboard', () => {
  it('🔴 el contador de señas pendientes lleva a la lista de pendientes', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json({
      date_from: '2026-07-20', date_to: '2026-07-20',
      turnos: { total_en_periodo: 0, por_estado: {}, hoy: 0 },
      clientes: { total_activos: 0, nuevos_en_periodo: 0 },
      recordatorios_enviados_en_periodo: 0,
      senas_pendientes: 3,
      facturacion: {
        facturas_emitidas_en_periodo: 0,
        caja: { ingresos_en_periodo: 0, egresos_en_periodo: 0, saldo_periodo: 0, saldo_total: 0 },
      },
    })))
    montar('/reportes')
    const enlace = (await screen.findByText('Señas pendientes')).closest('a')
    expect(enlace).toHaveAttribute('href', '/senas?estado=pending')
    expect(enlace).toHaveTextContent('3')
  })
})

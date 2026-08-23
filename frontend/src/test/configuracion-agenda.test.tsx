// Las tres secciones de Configuración que parametrizan la agenda.
//
// Antes del 2026-08-22 no había ninguna pantalla para esto: los endpoints
// existían desde el MVP y sólo se llegaba a ellos por API o por el seed. Lo que
// se prueba acá es que **un alta se hace dando de alta** — qué se manda, a
// dónde, y qué queda a la vista después.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SucursalesCard } from '../pages/configuracion/sucursales'
import { ServiciosCard } from '../pages/configuracion/servicios'
import { RecursosCard } from '../pages/configuracion/recursos'

const SUCURSAL = {
  id: 'centro', name: 'Centro', active: true,
  timezone: 'America/Argentina/Buenos_Aires', phone: null, address: 'Rivadavia 100',
}
const RECURSO = { id: 'box-1', name: 'Box 1', branch_id: 'centro', active: true }
const SERVICIO = { id: 'corte', name: 'Corte', duration_minutes: 30, active: true }

let fetchMock: ReturnType<typeof vi.fn>
let pedidos: { url: string; metodo: string; cuerpo: unknown }[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

/** Sirve cada ruta EXACTA; cualquier otra devuelve una lista vacía.
 *
 *  🔴 Exacta y no por subcadena. Con `includes`, `/resources/box-1/blocks` cae
 *  en la clave `/resources` y el componente de bloqueos recibe una lista de
 *  recursos: revienta al leer `starts_at`, la pantalla queda vacía, y tres
 *  tests fallan con un mensaje que no tiene nada que ver con lo que dicen
 *  medir. Pasó escribiendo este archivo. */
function servir(rutas: Record<string, unknown>) {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const u = String(url)
    pedidos.push({
      url: u,
      metodo: init?.method ?? 'GET',
      cuerpo: init?.body ? JSON.parse(String(init.body)) : null,
    })
    return Promise.resolve(json(rutas[u] ?? []))
  })
}

function montar(nodo: React.ReactNode) {
  return render(<MemoryRouter>{nodo}</MemoryRouter>)
}

function mandado(url: string, metodo = 'POST') {
  return pedidos.find((p) => p.url === url && p.metodo === metodo)
}

beforeEach(() => {
  fetchMock = vi.fn()
  pedidos = []
  vi.stubGlobal('fetch', fetchMock)
})

// ── Sucursales ─────────────────────────────────────────────────────────────

describe('Sucursales', () => {
  it('lista lo que hay, con su huso', async () => {
    servir({ '/branches': [SUCURSAL] })
    montar(<SucursalesCard />)
    expect(await screen.findByText('Centro')).toBeInTheDocument()
    // `getAllBy`: el huso sale dos veces, en la fila de la lista y en el
    // selector del formulario.
    expect(screen.getAllByText(/Argentina \(UTC-3\)/).length).toBeGreaterThan(0)
  })

  it('🔴 el alta manda el huso de Argentina, no UTC', async () => {
    // Es el default de la lista de husos y el del backend. Con UTC la agenda
    // muestra todos los turnos tres horas corridos (ADR-030).
    servir({ '/branches': [] })
    montar(<SucursalesCard />)
    await userEvent.type(await screen.findByLabelText('Nombre'), 'Peluquería Norte')
    await userEvent.click(screen.getByRole('button', { name: 'Crear' }))
    await waitFor(() => expect(mandado('/branches')).toBeTruthy())
    expect(mandado('/branches')!.cuerpo).toMatchObject({
      // El identificador sale del nombre, sin acentos ni espacios.
      id: 'peluqueria-norte',
      name: 'Peluquería Norte',
      timezone: 'America/Argentina/Buenos_Aires',
      active: true,
    })
  })

  it('al elegir una sucursal aparece su horario de atención', async () => {
    servir({ '/branches/centro/hours': [], '/branches': [SUCURSAL] })
    montar(<SucursalesCard />)
    await userEvent.click(await screen.findByText('Centro'))
    expect(await screen.findByText('Horario de atención')).toBeInTheDocument()
  })
})

// ── Las ventanas semanales ────────────────────────────────────────────────

describe('Ventanas semanales', () => {
  it('🔴 "Lunes a viernes" carga los cinco días de una', async () => {
    // Sin este atajo, el horario más común del mundo son cinco altas idénticas
    // a mano, por cada recurso y por cada sucursal.
    servir({ '/branches/centro/hours': [], '/branches': [SUCURSAL] })
    montar(<SucursalesCard />)
    await userEvent.click(await screen.findByText('Centro'))
    await screen.findByText('Horario de atención')
    await userEvent.click(screen.getByRole('button', { name: 'Lunes a viernes' }))

    await waitFor(() => {
      const altas = pedidos.filter(
        (p) => p.url === '/branches/centro/hours' && p.metodo === 'POST')
      expect(altas.map((a) => (a.cuerpo as { weekday: number }).weekday)).toEqual([0, 1, 2, 3, 4])
      expect(altas[0].cuerpo).toEqual({
        weekday: 0, starts_at: '09:00:00', ends_at: '19:00:00',
      })
    })
  })

  it('🔴 el control — no pisa un día que ya estaba cargado', async () => {
    // Cargar el lunes de 14 a 20 y después apretar el atajo no puede duplicar
    // el lunes: la sucursal quedaría con dos horarios contradictorios el mismo
    // día y el motor aceptaría los dos.
    servir({
      '/branches/centro/hours': [
        { id: 1, weekday: 0, starts_at: '14:00:00', ends_at: '20:00:00' },
      ],
      '/branches': [SUCURSAL],
    })
    montar(<SucursalesCard />)
    await userEvent.click(await screen.findByText('Centro'))
    await screen.findByText('Horario de atención')
    await userEvent.click(screen.getByRole('button', { name: 'Lunes a viernes' }))

    await waitFor(() => {
      const altas = pedidos.filter(
        (p) => p.url === '/branches/centro/hours' && p.metodo === 'POST')
      expect(altas.map((a) => (a.cuerpo as { weekday: number }).weekday)).toEqual([1, 2, 3, 4])
    })
  })

  it('un horario cargado se puede borrar', async () => {
    servir({
      '/branches/centro/hours': [
        { id: 7, weekday: 2, starts_at: '09:00:00', ends_at: '19:00:00' },
      ],
      '/branches': [SUCURSAL],
    })
    montar(<SucursalesCard />)
    await userEvent.click(await screen.findByText('Centro'))
    expect(await screen.findByText('Miércoles')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Borrar Miércoles 09:00'))
    await waitFor(() => expect(mandado('/branches/centro/hours/7', 'DELETE')).toBeTruthy())
  })
})

// ── Servicios ──────────────────────────────────────────────────────────────

describe('Servicios', () => {
  it('el alta manda la duración, que es lo que ocupa el turno', async () => {
    servir({ '/services': [], '/branches': [SUCURSAL] })
    montar(<ServiciosCard />)
    await userEvent.type(await screen.findByLabelText('Nombre'), 'Color')
    const duracion = screen.getByLabelText('Duración (minutos)')
    await userEvent.clear(duracion)
    await userEvent.type(duracion, '90')
    await userEvent.click(screen.getByRole('button', { name: 'Crear' }))
    await waitFor(() => expect(mandado('/services')).toBeTruthy())
    expect(mandado('/services')!.cuerpo).toEqual({
      id: 'color', name: 'Color', duration_minutes: 90, active: true,
    })
  })

  it('🔴 los honorarios se cargan por sucursal', async () => {
    servir({
      '/services/corte/prices': [],
      '/services': [SERVICIO],
      '/branches': [SUCURSAL],
    })
    montar(<ServiciosCard />)
    await userEvent.click(await screen.findByText('Corte'))
    await userEvent.type(await screen.findByLabelText('Centro'), '4500')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(mandado('/services/corte/prices', 'PUT')).toBeTruthy())
    expect(mandado('/services/corte/prices', 'PUT')!.cuerpo).toEqual({
      branch_id: 'centro', price: '4500',
    })
  })

  it('🔴 una sucursal sin precio se ve, no se esconde', async () => {
    // Un servicio sin precio en una sucursal se completa SIN facturar. Si la
    // sucursal no apareciera en la lista, esa ausencia sería invisible.
    servir({
      '/services/corte/prices': [],
      '/services': [SERVICIO],
      '/branches': [SUCURSAL],
    })
    montar(<ServiciosCard />)
    await userEvent.click(await screen.findByText('Corte'))
    expect(await screen.findByText('Sin precio')).toBeInTheDocument()
  })
})

// ── Recursos ───────────────────────────────────────────────────────────────

describe('Recursos', () => {
  it('el alta manda la sucursal elegida', async () => {
    servir({ '/resources': [], '/branches': [SUCURSAL] })
    montar(<RecursosCard />)
    await userEvent.type(await screen.findByLabelText('Nombre'), 'Sillón 2')
    await userEvent.click(screen.getByLabelText('Sucursal'))
    await userEvent.click(await screen.findByRole('option', { name: 'Centro' }))
    await userEvent.click(screen.getByRole('button', { name: 'Crear' }))
    await waitFor(() => expect(mandado('/resources')).toBeTruthy())
    expect(mandado('/resources')!.cuerpo).toEqual({
      id: 'sillon-2', name: 'Sillón 2', branch_id: 'centro', active: true,
    })
  })

  it('🔴 avisa que sin disponibilidad el recurso no recibe ningún turno', async () => {
    // Es la asimetría que deja la agenda muerta: el horario de la sucursal es
    // opt-in, la disponibilidad del recurso NO. Cargar sólo el primero -- que
    // es lo intuitivo -- hace que toda alta se rechace, sin ninguna pista.
    servir({
      '/resources/box-1/availability': [],
      '/resources': [RECURSO],
      '/branches': [SUCURSAL],
    })
    montar(<RecursosCard />)
    await userEvent.click(await screen.findByText('Box 1'))
    expect(await screen.findByText(/NO recibe ningún turno/)).toBeInTheDocument()
  })

  it('una excepción se puede cargar como cierre o como apertura', async () => {
    servir({
      '/resources/box-1/exceptions': [],
      '/resources': [RECURSO],
      '/branches': [SUCURSAL],
    })
    montar(<RecursosCard />)
    await userEvent.click(await screen.findByText('Box 1'))
    await screen.findByText('Excepciones por fecha')

    const fecha = screen.getByLabelText('Fecha')
    await userEvent.type(fecha, '2026-12-25')
    await userEvent.click(screen.getByLabelText('Qué hace'))
    await userEvent.click(await screen.findByRole('option', { name: 'Abre' }))
    await userEvent.click(screen.getByRole('button', { name: 'Agregar excepción' }))

    await waitFor(() => expect(mandado('/resources/box-1/exceptions')).toBeTruthy())
    expect(mandado('/resources/box-1/exceptions')!.cuerpo).toEqual({
      day: '2026-12-25', starts_at: '09:00:00', ends_at: '19:00:00', available: true,
    })
  })
})

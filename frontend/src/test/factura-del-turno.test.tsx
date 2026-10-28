// La factura de un turno completado y su nota de crédito (ADR-039).
//
// La nota la emite el motor; lo que se prueba acá es la pantalla: que muestre la factura y sus notas con el PDF de cada una,
// que el botón sea del administrador y del central, que pida el motivo, que pregunte por la plata (el kit, contra el motor)
// y que mande al backend exactamente lo que el backend espera.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FacturaDelTurno } from '../components/agenda/factura-del-turno'
import { etiquetaDeComprobante, importeEscrito } from '../lib/factura-del-turno'
import type { TurnoConRecurso } from '../components/agenda/datos'
import type { ComprobanteDelTurno, FacturaDelTurno as Detalle } from '../api'

const TURNO = { id: 't-1', status: 'completed' } as unknown as TurnoConRecurso

const FACTURA: ComprobanteDelTurno = {
  id: 7, tipo: 6, punto_venta: 3, numero: 12, fecha: '2026-10-28', total: 1000, cliente_razon: 'Ana Gómez',
  cae: '70123456789012', cae_vto: '2026-11-07', observaciones: '',
}
const NOTA: ComprobanteDelTurno = {
  ...FACTURA, id: 9, tipo: 8, numero: 2, total: 400, cae: '70123456789999', observaciones: 'Anula Factura B',
}
const SIN_NOTAS: Detalle = { factura: FACTURA, notas_credito: [], acreditado: 0, saldo_acreditable: 1000, puede_acreditar: true }
const CON_UNA_PARCIAL: Detalle = {
  factura: FACTURA, notas_credito: [NOTA], acreditado: 400, saldo_acreditable: 600, puede_acreditar: true,
}
const ACREDITADA: Detalle = {
  factura: FACTURA, notas_credito: [{ ...NOTA, total: 1000 }], acreditado: 1000, saldo_acreditable: 0, puede_acreditar: false,
}
const PLATA_A_DEVOLVER = {
  aplica: true, monto: 1000, excedente: 0, medios: [{ id: 'efectivo', label: 'Efectivo' }, { id: 'transferencia', label: 'Transferencia' }],
  medio_sugerido: 'efectivo', cliente_identificado: false, sin_turno: false,
}
const SIN_PLATA = { aplica: false, monto: 0, excedente: 0, medios: [], medio_sugerido: null, cliente_identificado: false, sin_turno: false }

type Pedido = { url: string; metodo: string; cuerpo: unknown }
let fetchMock: ReturnType<typeof vi.fn>
let pedidos: Pedido[]

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

/** El backend de la pantalla: la factura que se pide (puede cambiar tras emitir), la oferta de la plata y qué contesta el POST. */
function servir(opciones: {
  detalle?: Detalle | { status: number }
  despues?: Detalle
  oferta?: unknown
  post?: Response
}) {
  let detalle = opciones.detalle ?? SIN_NOTAS
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    pedidos.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
    if (metodo === 'POST') {
      if (opciones.despues) detalle = opciones.despues
      return Promise.resolve(opciones.post ?? json({ ...NOTA, id: 10 }))
    }
    if (u.includes('/nota-credito/destino')) return Promise.resolve(json(opciones.oferta ?? SIN_PLATA))
    if (u.endsWith('/factura')) {
      return Promise.resolve('status' in detalle ? json({ detail: 'x' }, detalle.status) : json(detalle))
    }
    return Promise.resolve(json({}))
  })
}

const montar = (props: { esAdmin?: boolean; soloLectura?: boolean; turno?: TurnoConRecurso } = {}) =>
  render(<FacturaDelTurno turno={props.turno ?? TURNO} esAdmin={props.esAdmin ?? true} soloLectura={props.soloLectura} />)

const posts = () => pedidos.filter((p) => p.metodo === 'POST')

beforeEach(() => {
  fetchMock = vi.fn()
  pedidos = []
  vi.stubGlobal('fetch', fetchMock)
})

describe('las funciones chicas', () => {
  it('el importe se escribe con coma o punto, de hasta dos decimales y mayor a cero', () => {
    expect(importeEscrito('1500,50')).toBe(1500.5)
    expect(importeEscrito(' 400.5 ')).toBe(400.5)
    for (const mal of ['', '0', '0,00', '-5', '12,345', 'abc', '1.000,50']) expect(importeEscrito(mal)).toBeNull()
  })

  it('la etiqueta dice el tipo y el número con ceros', () => {
    expect(etiquetaDeComprobante(FACTURA)).toBe('Factura B 0003-00000012')
    expect(etiquetaDeComprobante(NOTA)).toBe('Nota de crédito B 0003-00000002')
  })
})

describe('la factura del turno', () => {
  it('🔴 muestra la factura con su CAE y el PDF, que es el del motor', async () => {
    servir({})
    montar()
    const seccion = await screen.findByTestId('factura-del-turno')
    expect(within(seccion).getByText('Factura B 0003-00000012')).toBeInTheDocument()
    expect(within(seccion).getByText(/CAE 70123456789012/)).toBeInTheDocument()
    expect(within(seccion).getByRole('link', { name: /PDF de Factura B 0003-00000012/ }))
      .toHaveAttribute('href', '/api/facturas/7/pdf')
    expect(pedidos[0].url).toBe('/appointments/t-1/factura')
  })

  it('un turno que no está completado no pide nada ni muestra nada', () => {
    servir({})
    const { container } = montar({ turno: { id: 't-2', status: 'confirmed' } as unknown as TurnoConRecurso })
    expect(container).toBeEmptyDOMElement()
    expect(pedidos).toEqual([])
  })

  it.each([404, 403])('sin factura (%i) no se dibuja nada', async (status) => {
    servir({ detalle: { status } })
    const { container } = montar()
    await waitFor(() => expect(pedidos.length).toBe(1))
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('las notas de crédito se listan con su PDF y lo acreditado', async () => {
    servir({ detalle: CON_UNA_PARCIAL })
    montar()
    const nota = await screen.findByTestId('nota-de-credito')
    expect(within(nota).getByText('Nota de crédito B 0003-00000002')).toBeInTheDocument()
    expect(within(nota).getByRole('link', { name: /PDF de Nota de crédito B/ })).toHaveAttribute('href', '/api/facturas/9/pdf')
    expect(screen.getByTestId('acreditado')).toHaveTextContent(/Acreditado .*400,00 de .*1\.000,00.*quedan .*600,00/)
  })

  it('una factura acreditada por completo ya no ofrece la nota', async () => {
    servir({ detalle: ACREDITADA })
    montar()
    await screen.findByTestId('factura-del-turno')
    expect(screen.queryByRole('button', { name: /Nota de crédito/ })).not.toBeInTheDocument()
  })
})

describe('quién ve el botón', () => {
  it('🔴 el administrador, en la web, lo ve', async () => {
    servir({})
    montar()
    expect(await screen.findByRole('button', { name: /Nota de crédito/ })).toBeInTheDocument()
  })

  it('🔴 el staff ve la factura pero no el botón', async () => {
    servir({})
    montar({ esAdmin: false })
    await screen.findByTestId('factura-del-turno')
    expect(screen.queryByRole('button', { name: /Nota de crédito/ })).not.toBeInTheDocument()
  })

  it('🔴 en el equipo del local sin conexión no hay botón y se dice dónde se hace', async () => {
    servir({})
    montar({ soloLectura: true })
    await screen.findByTestId('factura-del-turno')
    expect(screen.queryByRole('button', { name: /Nota de crédito/ })).not.toBeInTheDocument()
    expect(screen.getByText(/se emite desde la web/)).toBeInTheDocument()
  })
})

describe('emitir la nota', () => {
  const abrir = async () => {
    await userEvent.click(await screen.findByRole('button', { name: /^Nota de crédito$/ }))
    return screen.findByRole('dialog')
  }
  const emitir = () => screen.getByRole('button', { name: 'Emitir nota de crédito' })

  it('🔴 confirma sobre qué factura y no emite sin motivo', async () => {
    servir({})
    montar()
    const dialogo = await abrir()
    expect(within(dialogo).getByText(/Anula ante ARCA la Factura B 0003-00000012/)).toBeInTheDocument()
    expect(within(dialogo).getByText(/no se puede deshacer/)).toBeInTheDocument()
    expect(emitir()).toBeDisabled()

    await userEvent.type(within(dialogo).getByLabelText('Motivo'), 'xx')
    expect(emitir()).toBeDisabled()
    await userEvent.type(within(dialogo).getByLabelText('Motivo'), 'xxx')
    await waitFor(() => expect(emitir()).toBeEnabled())
  })

  it('🔴 la nota total sin plata cobrada manda sólo el motivo y refresca la factura', async () => {
    servir({ despues: ACREDITADA })
    montar()
    const dialogo = await abrir()
    await userEvent.type(within(dialogo).getByLabelText('Motivo'), '  Se facturó   el servicio equivocado ')
    await waitFor(() => expect(emitir()).toBeEnabled())
    await userEvent.click(emitir())

    await waitFor(() => expect(posts().length).toBe(1))
    expect(posts()[0].url).toBe('/appointments/t-1/nota-credito')
    // El motivo viaja sin espacios de más, y no hay `importe` (total) ni `destino` (no hay plata que mover).
    expect(posts()[0].cuerpo).toEqual({ motivo: 'Se facturó el servicio equivocado' })
    // Cierra el diálogo y vuelve a pedir la factura: ahora está acreditada y el botón se fue.
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByTestId('nota-de-credito')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Nota de crédito$/ })).not.toBeInTheDocument()
  })

  it('🔴 con plata cobrada hay que elegir qué pasa con ella, y se manda el destino y el medio', async () => {
    servir({ oferta: PLATA_A_DEVOLVER, despues: ACREDITADA })
    montar()
    const dialogo = await abrir()
    expect(await within(dialogo).findByText('¿Qué pasa con la plata?')).toBeInTheDocument()
    await userEvent.type(within(dialogo).getByLabelText('Motivo'), 'Cobro duplicado')
    expect(emitir()).toBeDisabled()

    await userEvent.click(within(dialogo).getByRole('radio', { name: /Devolver/ }))
    // El medio con el que se cobró viene sugerido: no hace falta elegirlo.
    await waitFor(() => expect(emitir()).toBeEnabled())
    expect(within(dialogo).getByRole('radio', { name: /Dejar a favor/ })).toBeDisabled()
    await userEvent.click(emitir())

    await waitFor(() => expect(posts().length).toBe(1))
    expect(posts()[0].cuerpo).toEqual({ motivo: 'Cobro duplicado', destino: 'devolver', medio_pago: 'efectivo' })
  })

  it('🔴 la nota parcial manda el importe como texto de dos decimales y pregunta la plata por ese importe', async () => {
    servir({ oferta: { ...PLATA_A_DEVOLVER, monto: 400.5 }, despues: CON_UNA_PARCIAL })
    montar()
    const dialogo = await abrir()
    await userEvent.click(within(dialogo).getByRole('radio', { name: 'Parcial' }))
    await userEvent.type(within(dialogo).getByLabelText(/Importe a acreditar/), '400,5')
    await userEvent.type(within(dialogo).getByLabelText('Motivo'), 'Descuento acordado')
    await userEvent.click(await within(dialogo).findByRole('radio', { name: /Devolver/ }))
    await waitFor(() => expect(emitir()).toBeEnabled())
    expect(pedidos.some((p) => p.url === '/appointments/t-1/nota-credito/destino?importe=400.5')).toBe(true)
    await userEvent.click(emitir())

    await waitFor(() => expect(posts().length).toBe(1))
    expect(posts()[0].cuerpo).toEqual({
      motivo: 'Descuento acordado', importe: '400.50', destino: 'devolver', medio_pago: 'efectivo',
    })
  })

  it('un importe mayor a lo que queda se marca y no se puede emitir', async () => {
    servir({})
    montar()
    const dialogo = await abrir()
    await userEvent.click(within(dialogo).getByRole('radio', { name: 'Parcial' }))
    await userEvent.type(within(dialogo).getByLabelText(/Importe a acreditar/), '1500')
    await userEvent.type(within(dialogo).getByLabelText('Motivo'), 'Descuento acordado')
    expect(within(dialogo).getByText(/Poné un monto de hasta/)).toBeInTheDocument()
    expect(emitir()).toBeDisabled()
  })

  it('🔴 una factura que ya tiene una nota sólo admite otra por un importe', async () => {
    servir({ detalle: CON_UNA_PARCIAL })
    montar()
    const dialogo = await abrir()
    expect(within(dialogo).getByRole('radio', { name: /Total/ })).toBeDisabled()
    expect(within(dialogo).getByRole('radio', { name: 'Parcial' })).toBeChecked()
    expect(within(dialogo).getByText(/Se puede acreditar hasta .*600,00/)).toBeInTheDocument()
  })

  it('🔴 si el backend la rechaza (409) se dice por qué y el diálogo sigue abierto para corregir', async () => {
    servir({ post: json({ detail: 'Esa factura ya tiene una nota de crédito.' }, 409) })
    montar()
    const dialogo = await abrir()
    await userEvent.type(within(dialogo).getByLabelText('Motivo'), 'Se facturó mal')
    await waitFor(() => expect(emitir()).toBeEnabled())
    await userEvent.click(emitir())

    expect(await within(dialogo).findByRole('alert')).toHaveTextContent('Esa factura ya tiene una nota de crédito.')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(emitir()).toBeEnabled()
  })

  it('cancelar no manda nada', async () => {
    servir({})
    montar()
    const dialogo = await abrir()
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(posts()).toEqual([])
  })
})

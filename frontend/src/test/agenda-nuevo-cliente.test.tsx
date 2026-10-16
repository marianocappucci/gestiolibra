// «Nuevo turno»: el cliente que todavía no está cargado se da de alta ahí mismo (ADR-071, libra-ui v0.158.0).
//
// 🔴 **Lo que se mide es el CABLE y el resultado**: el alta va a `POST /clients` con el payload de `ClientCreate` (lo vacío como `null`, no
// como `''`), el recién creado queda ELEGIDO en el campo, y el turno se manda con su id. Quien atiende no es admin —por eso el backend le
// abrió el alta (tests/test_clients.py)—: acá se monta la agenda como staff (`esAdmin={false}`).
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
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
const CREADO = {
  id: 'dora-id', name: 'Dora Pérez', phone: '1155550000', email: null, active: true,
  cuit: null, condicion_iva: null,
}

type Pedido = { url: string; metodo: string; cuerpo: unknown }

let fetchMock: ReturnType<typeof vi.fn>
let pedidos: Pedido[]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

function servir({ alta = () => json(CREADO, 201) as Response } = {}) {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    pedidos.push({ url: u, metodo, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
    if (metodo === 'POST' && u === '/clients') return Promise.resolve(alta())
    if (metodo === 'POST' && u === '/appointments') return Promise.resolve(json({ id: 't-nuevo' }, 201))
    if (u.includes('/agenda?')) return Promise.resolve(json([]))
    if (u.includes('/resources')) return Promise.resolve(json([RECURSO]))
    if (u.includes('/branches')) return Promise.resolve(json([SUCURSAL]))
    if (u.includes('/services')) return Promise.resolve(json([SERVICIO]))
    if (u.includes('/clients')) return Promise.resolve(json([CLIENTE]))
    return Promise.resolve(json([]))
  })
}

async function abrirNuevoTurno() {
  render(
    <MemoryRouter initialEntries={[`/agenda?dia=${LUNES}`]}>
      <Routes>
        <Route path="/agenda" element={<Agenda esAdmin={false} />} />
      </Routes>
    </MemoryRouter>,
  )
  await waitFor(() => expect(document.querySelectorAll('[data-columna]')).toHaveLength(7))
  await userEvent.click(screen.getByRole('button', { name: /Nuevo turno/ }))
  return screen.findByRole('dialog')
}

const altas = () => pedidos.filter((p) => p.url === '/clients' && p.metodo === 'POST')

beforeEach(() => {
  fetchMock = vi.fn()
  pedidos = []
  vi.stubGlobal('fetch', fetchMock)
})

describe('Nuevo turno: dar de alta al cliente ahí mismo', () => {
  it('🔴 crear el cliente manda POST /clients y lo deja elegido', async () => {
    servir()
    const dialogo = await abrirNuevoTurno()

    // El control: el campo arranca vacío y el botón de alta está.
    const campo = within(dialogo).getByRole('combobox', { name: 'Cliente' })
    expect(campo).toHaveValue('')
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Agregar nuevo cliente' }))

    const panel = within(dialogo).getByRole('group', { name: 'Nuevo cliente' })
    await userEvent.type(within(panel).getByLabelText(/^Nombre/), '  Dora Pérez ')
    await userEvent.type(within(panel).getByLabelText('Teléfono'), '1155550000')
    await userEvent.click(within(panel).getByRole('button', { name: 'Crear cliente' }))

    await waitFor(() => expect(altas()).toHaveLength(1))
    // El payload de `ClientCreate`: lo que no se pidió viaja como null, y el nombre sin los espacios de los costados.
    expect(altas()[0].cuerpo).toEqual({
      name: 'Dora Pérez', phone: '1155550000', email: null, cuit: null, condicion_iva: null,
    })

    // Quedó elegido (el panel se cierra) y está en la lista del campo junto al que ya existía.
    await waitFor(() => expect(within(dialogo).queryByRole('group', { name: 'Nuevo cliente' })).not.toBeInTheDocument())
    expect(within(dialogo).getByRole('combobox', { name: 'Cliente' })).toHaveValue('Dora Pérez')
  })

  it('🔴 el turno se manda con el id del cliente recién creado', async () => {
    servir()
    const dialogo = await abrirNuevoTurno()

    await userEvent.click(within(dialogo).getByLabelText('Servicio'))
    await userEvent.click(await screen.findByText('Corte'))
    await userEvent.click(within(dialogo).getByRole('button', { name: 'Agregar nuevo cliente' }))
    const panel = within(dialogo).getByRole('group', { name: 'Nuevo cliente' })
    await userEvent.type(within(panel).getByLabelText(/^Nombre/), 'Dora Pérez')
    await userEvent.click(within(panel).getByRole('button', { name: 'Crear cliente' }))
    await waitFor(() => expect(within(dialogo).getByRole('combobox', { name: 'Cliente' })).toHaveValue('Dora Pérez'))

    await userEvent.click(within(dialogo).getByRole('button', { name: 'Crear turno' }))
    await waitFor(() => {
      const turno = pedidos.find((p) => p.url === '/appointments' && p.metodo === 'POST')
      expect(turno?.cuerpo).toMatchObject({ client_id: 'dora-id', service_id: 'corte' })
    })
  })

  it('si el alta falla muestra el error dentro del panel y no deja nada elegido', async () => {
    servir({ alta: () => json({ detail: 'client already exists' }, 409) })
    const dialogo = await abrirNuevoTurno()

    await userEvent.click(within(dialogo).getByRole('button', { name: 'Agregar nuevo cliente' }))
    const panel = within(dialogo).getByRole('group', { name: 'Nuevo cliente' })
    await userEvent.type(within(panel).getByLabelText(/^Nombre/), 'Dora Pérez')
    await userEvent.click(within(panel).getByRole('button', { name: 'Crear cliente' }))

    expect(await within(panel).findByRole('alert')).toHaveTextContent('client already exists')
    expect(within(dialogo).getByRole('combobox', { name: 'Cliente' })).toHaveValue('')
    // Lo cargado no se pierde.
    expect(within(panel).getByLabelText(/^Nombre/)).toHaveValue('Dora Pérez')
  })
})

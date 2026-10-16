// «Consultar en ARCA» en el alta de un cliente: completa nombre y condición de IVA con el padrón, sin pisar lo
// ya escrito, y si ARCA no está habilitada manda al tutorial de Configuración.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { Clientes } from '../pages/Clientes'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true },
    loading: false, login: vi.fn(), logout: vi.fn(),
  }),
}))

const json = (estado: number, cuerpo: unknown) =>
  Promise.resolve(new Response(JSON.stringify(cuerpo), { status: estado, headers: { 'content-type': 'application/json' } }))

let consultar: (url: string) => Promise<Response>

beforeEach(() => {
  consultar = () => json(200, {
    nombre: 'ACME SA', domicilio: 'Ruta 8', iva_condition: 'Monotributista', estado: 'ACTIVO',
  })
  vi.stubGlobal('fetch', vi.fn((url: string) => (
    String(url).startsWith('/api/consultar-cuit/') ? consultar(String(url)) : json(200, [])
  )))
})

async function abrirAlta() {
  const usuario = userEvent.setup()
  render(<Clientes />)
  await usuario.click(await screen.findByRole('button', { name: /nuevo cliente/i }))
  return usuario
}

it('con el CUIT cargado completa el nombre y la condición de IVA, y el botón mide 44 px bajo lg', async () => {
  const usuario = await abrirAlta()
  await usuario.type(screen.getByRole('textbox', { name: 'CUIT' }), '30-71111111-4')
  const boton = screen.getByRole('button', { name: /Consultar en ARCA/ })
  expect(boton).toHaveClass('max-lg:h-11')
  await usuario.click(boton)

  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Nombre' })).toHaveValue('ACME SA'))
  expect(fetch).toHaveBeenCalledWith('/api/consultar-cuit/30711111114', { credentials: 'include' })
  expect(screen.getByRole('combobox', { name: 'Condición de IVA' })).toHaveTextContent('Monotributista')
})

it('no pisa un nombre ya escrito: pregunta', async () => {
  const usuario = await abrirAlta()
  await usuario.type(screen.getByRole('textbox', { name: 'Nombre' }), 'Panadería del Sol')
  await usuario.type(screen.getByRole('textbox', { name: 'CUIT' }), '30-71111111-4')
  await usuario.click(screen.getByRole('button', { name: /Consultar en ARCA/ }))

  expect(await screen.findByRole('group', { name: /distintos de los cargados/ })).toHaveTextContent('Nombre: ACME SA')
  expect(screen.getByRole('textbox', { name: 'Nombre' })).toHaveValue('Panadería del Sol')
  await usuario.click(screen.getByRole('button', { name: 'Reemplazar con los de ARCA' }))
  expect(screen.getByRole('textbox', { name: 'Nombre' })).toHaveValue('ACME SA')
})

it('sin certificados de ARCA (503) dice qué falta y enlaza al tutorial de Configuración', async () => {
  consultar = () => json(503, { error: 'Configurá los certificados ARCA en Configuración para habilitar la consulta de CUIT.' })
  const usuario = await abrirAlta()
  await usuario.type(screen.getByRole('textbox', { name: 'CUIT' }), '30-71111111-4')
  await usuario.click(screen.getByRole('button', { name: /Consultar en ARCA/ }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Configurá los certificados ARCA en Configuración')
  expect(screen.getByRole('link', { name: /Cómo habilitar el servicio de Padrón/ }))
    .toHaveAttribute('href', '/configuracion?seccion=integraciones&integracion=arca#tutorial-padron-a13')
})

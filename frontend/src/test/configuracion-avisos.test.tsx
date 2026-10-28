// La sección «Avisos» de Configuración (ADR-040): la conexión de WhatsApp y el registro de los recordatorios que salieron.
//
// Las dos piezas son del kit (libra-ui ADR-097) y tienen sus propios tests allá. Lo que se prueba acá es **lo que monta este producto**:
// que la sección esté en Configuración, que apunte a `/api/avisos`, que el administrador vea el destino entero (la pieza lo enmascara
// si no se le dice `esAdmin`), que el tipo `recordatorio` se lea en criollo y que una demo se entienda como demo.
import { render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Configuracion } from '../pages/Configuracion'
import { AvisosSeccion } from '../pages/configuracion/avisos'
import { etiquetaDelTipo } from '@/lib/avisos'

let fetchMock: ReturnType<typeof vi.fn>
let pedidos: { url: string; metodo: string }[] = []

const CONFIG = {
  whatsapp: {
    modo: 'registro', modos: ['apagado', 'registro', 'evolution'], url: '', instancia: '', apikey_cargada: false,
    disponible: true, motivo: '',
  },
  email: { disponible: true },
}

const ENVIO = {
  id: 1, canal: 'whatsapp', clave: 'agenda:t1:24h', tipo: 'recordatorio', destino: '5491155551234', asunto: '',
  cuerpo: '*Recordatorio de turno*', plantilla: '', variables: {}, proveedor: 'registro', estado: 'registrado', intentos: 1,
  detalle: '', id_externo: '', enviado_at: '', created_at: '2026-10-28 09:30:15', updated_at: '2026-10-28 09:30:15',
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function servir(demo: boolean | 'falla') {
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    const u = String(url)
    pedidos.push({ url: u, metodo: init?.method ?? 'GET' })
    if (u === '/api/avisos/config') return Promise.resolve(json(CONFIG))
    if (u.startsWith('/api/avisos/envios')) return Promise.resolve(json([ENVIO]))
    if (u === '/auth/demo') return Promise.resolve(demo === 'falla' ? json({ detail: 'x' }, 500) : json({ enabled: demo, username: 'demo' }))
    return Promise.resolve(json([]))
  })
}

beforeEach(() => {
  pedidos = []
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

describe('la sección Avisos de Configuración', () => {
  it('🔴 está en Configuración y se abre por la URL', async () => {
    servir(false)
    render(<MemoryRouter initialEntries={['/configuracion?seccion=avisos']}><Configuracion /></MemoryRouter>)

    expect(await screen.findByRole('tab', { name: /Avisos/ })).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(pedidos.map((p) => p.url)).toContain('/api/avisos/config'))
    expect(await screen.findByText('Registro de avisos')).toBeInTheDocument()
  })

  it('pide la configuración y el registro al router del motor, en `/api/avisos`', async () => {
    servir(false)
    render(<AvisosSeccion />)
    await screen.findByText('Registro de avisos')
    const urls = pedidos.map((p) => p.url)
    expect(urls).toContain('/api/avisos/config')
    expect(urls.some((u) => u.startsWith('/api/avisos/envios'))).toBe(true)
  })

  it('🔴 el administrador ve el teléfono entero y el tipo en criollo', async () => {
    servir(false)
    render(<AvisosSeccion />)
    // Sin `esAdmin` la pieza lo enmascara (`••••••••1234`): el registro existe para contestar «¿le llegó a Ana?».
    expect(await screen.findByText('5491155551234')).toBeInTheDocument()
    expect(screen.getByText('Recordatorio de turno')).toBeInTheDocument()
    expect(screen.queryByText('••••••••1234')).toBeNull()
  })

  it('en una demo, Evolution no se ofrece y la pantalla lo dice', async () => {
    servir(true)
    render(<AvisosSeccion />)
    await screen.findByText('Registro de avisos')
    expect(await screen.findByText(/Esto es una demo: los avisos por WhatsApp sólo se anotan/)).toBeInTheDocument()
    expect(pedidos.map((p) => p.url)).toContain('/auth/demo')
  })

  it('fuera de una demo no hay aviso de demo', async () => {
    servir(false)
    render(<AvisosSeccion />)
    await screen.findByText('Registro de avisos')
    await waitFor(() => expect(pedidos.map((p) => p.url)).toContain('/auth/demo'))
    expect(screen.queryByText(/Esto es una demo/)).toBeNull()
  })

  it('si no se sabe si es una demo, la sección anda igual', async () => {
    servir('falla')
    render(<AvisosSeccion />)
    expect(await screen.findByText('Registro de avisos')).toBeInTheDocument()
  })

  it('un tipo que el producto no rotula se muestra tal cual', () => {
    expect(etiquetaDelTipo('recordatorio')).toBe('Recordatorio de turno')
    expect(etiquetaDelTipo('otro_tipo')).toBe('otro_tipo')
  })

  it('🔴 el registro se monta con `esAdmin` (fuente: sin esa prop la pieza enmascara el destino)', () => {
    const fuente = readFileSync(join(process.cwd(), 'src', 'pages', 'configuracion', 'avisos.tsx'), 'utf8')
    expect(fuente).toMatch(/<RegistroDeAvisos[^>]*\besAdmin\b/)
  })
})

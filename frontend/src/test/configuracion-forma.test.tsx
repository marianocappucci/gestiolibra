// La FORMA de la pantalla de Configuración de este producto.
//
// La pantalla la rinde `libra-ui/Configuracion`, que tiene sus propios tests:
// lo que se prueba acá es **lo que declara Gestiolibra**, que es lo único que
// vive en este repo y lo único que puede divergir del resto de la familia sin
// que nadie lo note.
//
// 🔴 Y hay un dato que si se escribe mal no rompe nada y arruina la pantalla
// igual: el **slug de la empresa de ARCA**. `services/billing.py` lee la
// configuración de facturación con `EMPRESA = "negocio"`. En una instancia que
// todavía no tiene fila, el primer guardado la crea — y si la crea como
// `default`, ese servicio no la lee nunca: el admin sube el certificado, la
// pantalla dice "Guardado", y al emitir la primera factura el producto contesta
// que ARCA no está configurado.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Configuracion } from '../pages/Configuracion'

let pedidos: { url: string; metodo: string; cuerpo: unknown }[] = []

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  pedidos = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    const metodo = init?.method ?? 'GET'
    pedidos.push({ url: u, metodo, cuerpo: init?.body ?? null })

    if (u.includes('/logo')) return Promise.resolve(new Response('', { status: 404 }))
    if (u.includes('/admin/smtp')) {
      return Promise.resolve(json({
        origen: 'entorno', host: '', port: 587, user: '', from_email: '', from_name: '',
        password_definida: false, password_indescifrable: false, configurado: false,
      }))
    }
    if (u.includes('/api/config/mercadopago')) {
      return Promise.resolve(json({
        mp_access_token: '', mp_access_token_cargado: false,
        mp_webhook_secret: '', mp_webhook_secret_cargado: false,
        mp_concepto_descripcion: '', mp_iva_rate: '0',
        mp_user_id: '', mp_pos_id: '', mp_auto_facturar_ventas: false,
      }))
    }
    if (u.includes('/config/arca/estado')) {
      return Promise.resolve(json({ configurado: false }))
    }
    // Instancia nueva: todavía no hay fila de ARCA. `null` y no `[]` — `[]` es
    // truthy y el formulario lo leería como una config con todo en `undefined`.
    if (u.includes('/config/arca')) return Promise.resolve(json(null))
    if (u.includes('/api/config/empresa')) {
      return Promise.resolve(json({
        empresa_nombre: '', empresa_direccion: '', empresa_cuit: '', empresa_telefono: '',
        empresa_email: '', empresa_iibb: '', empresa_iva_condition: 'Monotributista',
        empresa_inicio_actividades: '',
      }))
    }
    return Promise.resolve(json([]))
  }))
})

const montar = (ruta = '/configuracion') =>
  render(<MemoryRouter initialEntries={[ruta]}><Configuracion /></MemoryRouter>)

describe('la Configuración de Gestiolibra', () => {
  it('tiene las pestañas de la familia, en el orden del arranque de un cliente', async () => {
    montar()

    const pestanias = (await screen.findAllByRole('tab')).map((t) => t.textContent)
    expect(pestanias).toEqual([
      'Empresa', 'Integraciones',
      // Primero dónde se atiende, después qué se ofrece y quién lo hace: al
      // revés, un servicio se carga sin poder ponerle precio —el precio es por
      // sucursal— y un recurso sin poder asignarlo.
      'Sucursales', 'Servicios', 'Recursos',
      'Datos / Backup',
    ])
  })

  it('las tres integraciones están, en la sub-navegación', async () => {
    montar('/configuracion?seccion=integraciones')

    await screen.findAllByRole('tab')
    // Anclado a los extremos: sin `^...$` el "Guardar MercadoPago" de la
    // tarjeta entra en la lista y el test cuenta cuatro botones de navegación
    // donde hay tres.
    const navegacion = screen.getAllByRole('button', {
      name: /^(MercadoPago|ARCA \/ AFIP|Email \/ SMTP)$/,
    })
    expect(navegacion.map((b) => b.textContent)).toEqual([
      'MercadoPago', 'ARCA / AFIP', 'Email / SMTP',
    ])
  })

  it('🔴 la fila de ARCA se crea con el slug que lee `services/billing.py`', async () => {
    // El defecto que esto impide es mudo: con `default` la pantalla guarda bien
    // y la facturación sigue diciendo que no está configurada.
    montar('/configuracion?seccion=integraciones&integracion=arca')
    const usuario = userEvent.setup()

    await usuario.click(await screen.findByRole('button', { name: /Guardar ARCA/ }))

    const put = pedidos.find((p) => p.url.includes('/config/arca') && p.metodo === 'PUT')
    expect(put, 'no llegó ningún PUT a /config/arca').toBeTruthy()
    expect(JSON.parse(String(put!.cuerpo)).empresa).toBe('negocio')
  })

  it('ARCA sube el certificado: ya no hay dónde tipear una ruta del servidor', async () => {
    // Es el cambio de fondo de la migración. Mientras hubo un campo de texto,
    // el alta no se podía hacer desde el navegador: alguien tenía que dejar el
    // .crt dentro del volumen del contenedor a mano.
    montar('/configuracion?seccion=integraciones&integracion=arca')

    // 🔑 Se nombra el ambiente: desde libra-ui v0.57.0 la tarjeta muestra los
    // DOS pares de credenciales, así que hay dos "Certificado (.crt)" y dos
    // "Clave privada (.key)" en la misma pantalla. Sin distinguirlos la consulta
    // es ambigua — y además no diría a qué par se refiere.
    expect(await screen.findByLabelText(/Certificado.*Homologaci/))
      .toHaveAttribute('type', 'file')
    expect(screen.getByLabelText(/Clave privada.*Homologaci/))
      .toHaveAttribute('type', 'file')
    // Y el par de producción también está, que es lo que el cambio agrega.
    expect(screen.getByLabelText(/Certificado.*Producci/)).toHaveAttribute('type', 'file')
    expect(screen.queryByLabelText(/Path del certificado/)).toBeNull()
  })

  it('MercadoPago tiene pestaña propia: hasta hoy sólo entraba por el backoffice', async () => {
    montar('/configuracion?seccion=integraciones&integracion=mercadopago')

    expect(await screen.findByLabelText(/Access Token/)).toBeInTheDocument()
    expect(screen.getByLabelText(/POS ID \(QR\)/)).toBeInTheDocument()
    // Y el tutorial de los cuatro datos, que es lo que hace la pestaña usable
    // por alguien que no tiene la cuenta de MercadoPago abierta al lado.
    expect(screen.getByText(/Access Token, User ID, POS ID y Webhook Secret/))
      .toBeInTheDocument()
  })

  it('los tutoriales nombran a Gestiolibra, no al producto del que salió la pantalla', async () => {
    montar('/configuracion?seccion=integraciones&integracion=email')

    expect(await screen.findAllByText(/contraseña de aplicación/)).not.toHaveLength(0)
    expect(screen.getByText('Gestiolibra')).toBeInTheDocument()
    expect(screen.queryByText('Contalibra')).toBeNull()
  })

  it('el botón de backup rápido está desde la primera pestaña', async () => {
    montar()

    expect(await screen.findByRole('link', { name: /Backup rápido/ }))
      .toHaveAttribute('href', '/api/config/backup-ahora')
  })
})

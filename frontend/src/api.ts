// Cliente HTTP delgado sobre la API de Gestiolibra. Cookie de sesion
// (gl_session) manejada por el browser via `credentials: "include"" --
// en dev el proxy de Vite (vite.config.ts) mantiene todo en el mismo
// origen (localhost:5173) para que la cookie funcione sin CORS; en
// produccion el build de este frontend se sirve desde el mismo proceso
// FastAPI (ver app/asgi.py), tambien mismo origen.
//
// El cliente base (ApiError/request/api) y el tipo User viven en
// libra-ui/api-client desde el 2026-07-26 (era byte-idéntico en
// Gestiolibra/MedLibra/VentaLibra -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md). Los tipos y
// endpoints de acá para abajo son propios de Gestiolibra.

export { api, ApiError, type User } from 'libra-ui/api-client'

import type { OpcionSelect } from 'libra-ui/SelectBuscable'

export type Branch = {
  id: string
  name: string
  active: boolean
  timezone: string
  phone: string | null
  address: string | null
}

export type Resource = {
  id: string
  name: string
  branch_id: string | null
  active: boolean
}

export type Service = {
  id: string
  name: string
  duration_minutes: number
  active: boolean
}

export type Client = {
  id: string
  name: string
  phone: string | null
  email: string | null
  active: boolean
  cuit: string | null
  condicion_iva: string | null
}

// --- opciones para los selects con busqueda (libra-ui/SelectBuscable) ------
//
// Viven aca, junto a los tipos, para que toda pantalla que elija un cliente o
// un servicio lo muestre y lo busque igual. El `hint` no es decorativo:
// ademas de desambiguar dos nombres parecidos, **entra en la busqueda**.
//
// En un negocio de servicios el telefono es el mejor discriminador: es lo que
// suele tenerse a mano cuando el cliente llama para sacar turno, y dos
// personas pueden llamarse casi igual.

export function opcionesCliente(clientes: Client[]): OpcionSelect[] {
  return clientes.map((c) => ({
    value: c.id,
    label: c.name,
    hint: [c.phone, c.active ? null : 'inactivo'].filter(Boolean).join(' · ') || undefined,
  }))
}

export function opcionesServicio(servicios: Service[]): OpcionSelect[] {
  return servicios.map((s) => ({
    value: s.id,
    label: s.name,
    // La duracion es lo que distingue dos servicios de nombre parecido
    // ("Corte" de 30 y "Corte + barba" de 45) al armar la agenda.
    hint: `${s.duration_minutes} min`,
  }))
}

export type AppointmentStatus =
  | 'pending' | 'confirmed' | 'in_progress' | 'completed' | 'cancelled' | 'no_show'

export const STATUS_LABELS: Record<AppointmentStatus, string> = {
  pending: 'Pendiente',
  confirmed: 'Confirmado',
  in_progress: 'En curso',
  completed: 'Completado',
  cancelled: 'Cancelado',
  no_show: 'No se presentó',
}

export type Appointment = {
  id: string
  resource_id: string
  service_id: string
  client_id: string
  starts_at: string
  ends_at: string
  status: AppointmentStatus
}

export type ArcaConfig = {
  empresa: string
  cuit: string
  punto_venta: number
  ambiente: string
  certificado_path: string
  clave_path: string
}

export type Factura = {
  id: number
  tipo: number
  punto_venta: number
  numero: number
  fecha: string
  cliente_cuit: string
  cliente_razon: string
  total: number
  cae: string
  cae_vto: string
}

// Solo A/B: Gestiolibra emite tipo A si el cliente es Responsable
// Inscripto, B en cualquier otro caso (ver app/services/billing.py).
export const TIPO_COMPROBANTE_LABELS: Record<number, string> = {
  1: 'Factura A',
  6: 'Factura B',
}

export type CompleteAppointmentResponse = {
  id: string
  status: AppointmentStatus
  factura: Factura | null
}

export type DashboardSummary = {
  date_from: string
  date_to: string
  turnos: {
    total_en_periodo: number
    por_estado: Record<AppointmentStatus, number>
    hoy: number
  }
  clientes: {
    total_activos: number
    nuevos_en_periodo: number
  }
  recordatorios_enviados_en_periodo: number
  senas_pendientes: number
  facturacion: {
    facturas_emitidas_en_periodo: number
    caja: {
      ingresos_en_periodo: number
      egresos_en_periodo: number
      saldo_periodo: number
      saldo_total: number
    }
  }
}

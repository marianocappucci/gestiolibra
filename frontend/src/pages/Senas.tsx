/** Las señas: las que hay que cobrar, las cobradas y las que se devolvieron.
 *
 *  Hasta el 2026-09-11 el backend las manejaba entero —pedir, cobrar, marcar
 *  fallida, devolver— y la única huella en pantalla era el contador
 *  "Señas pendientes" del Dashboard: un número que no llevaba a ningún lado.
 *  Esta pantalla es a donde lleva ahora.
 *
 *  **Admin-only**, como el backend (`GET /deposits` cuelga del router de
 *  cobros). El staff pide la seña desde el turno, en la agenda.
 *
 *  **El estado elegido vive en la URL** (`?estado=`), igual que la vista de la
 *  agenda: el Dashboard enlaza directo a las pendientes, y "atrás" vuelve.
 *
 *  ⚠️ **La hora del turno es la de la sucursal de su recurso**, no la del
 *  navegador (ADR-028): la misma cuenta que hace la agenda, con sus mismas
 *  funciones (`components/agenda/datos.ts`), y el formato del helper único.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { HandCoins } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import type { ColumnDef } from 'libra-ui/data-table'
import {
  api, ApiError, SENA_LABELS,
  type Branch, type Client, type EstadoSena, type Resource, type SenaConTurno, type Service,
} from '../api'
import { fechaHora } from '@/lib/fechas'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { BadgeSena, CobrarSenaDialog } from '@/components/senas'
import { formatMonto, nombreMedio, useMediosPago } from '@/lib/senas'
import { enHoraDePared, zonaPorRecurso } from '@/components/agenda/datos'

const TODAS = 'todas'
type Filtro = EstadoSena | typeof TODAS

/** El orden de las pestañas es el del trabajo: primero lo que hay que hacer. */
const FILTROS: { valor: Filtro; label: string }[] = [
  { valor: 'pending', label: 'Pendientes' },
  { valor: 'paid', label: 'Cobradas' },
  { valor: 'refunded', label: 'Devueltas' },
  { valor: 'failed', label: 'Fallidas' },
  { valor: TODAS, label: 'Todas' },
]

/** Sin `?estado=` —o con uno que no existe— se abre en las pendientes, que es
 *  por lo que se entra a esta pantalla. */
function filtroDeLaUrl(valor: string | null): Filtro {
  return FILTROS.some((f) => f.valor === valor) ? (valor as Filtro) : 'pending'
}

/** Una fila ya lista para mostrar: nombres resueltos y hora de pared. */
type Fila = SenaConTurno & {
  cliente: string
  servicio: string
  /** `aaaa-mm-ddTHH:mm:ss` en la zona de la sucursal, o `null` sin turno. */
  local: string | null
}

export function Senas() {
  const [params, setParams] = useSearchParams()
  const filtro = filtroDeLaUrl(params.get('estado'))

  const [senas, setSenas] = useState<SenaConTurno[]>([])
  const [clients, setClients] = useState<Client[]>([])
  const [services, setServices] = useState<Service[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const medios = useMediosPago()
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [errorAccion, setErrorAccion] = useState<string | null>(null)
  // `Fila` y no `SenaConTurno`: la confirmación de la devolución nombra al
  // cliente, y el nombre resuelto vive en la fila, no en la seña cruda.
  const [cobrando, setCobrando] = useState<Fila | null>(null)
  const [confirmando, setConfirmando] = useState<
    { sena: Fila; accion: 'refund' | 'mark-failed' } | null
  >(null)

  // El catálogo, una vez: sólo sirve para ponerle nombre a los ids.
  useEffect(() => {
    Promise.all([
      api.get<Client[]>('/clients'),
      api.get<Service[]>('/services'),
      api.get<Resource[]>('/resources'),
      api.get<Branch[]>('/branches'),
    ]).then(([c, s, r, b]) => {
      setClients(Array.isArray(c) ? c : [])
      setServices(Array.isArray(s) ? s : [])
      setResources(Array.isArray(r) ? r : [])
      setBranches(Array.isArray(b) ? b : [])
    }).catch(() => {
      // Sin catálogo la tabla muestra ids en vez de nombres, pero muestra las
      // señas: lo que no puede faltar es la plata, no el nombre.
    })
  }, [])

  const cargar = useCallback(async () => {
    setCargando(true)
    setError(null)
    try {
      const query = filtro === TODAS ? '' : `?status=${filtro}`
      const data = await api.get<SenaConTurno[]>(`/deposits${query}`)
      setSenas(Array.isArray(data) ? data : [])
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('No tenés acceso a las señas (requiere rol admin y el módulo "senas" habilitado en el plan).')
      } else {
        setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      }
      setSenas([])
    } finally {
      setCargando(false)
    }
  }, [filtro])

  useEffect(() => { void cargar() }, [cargar])

  const filas = useMemo<Fila[]>(() => {
    const zonas = zonaPorRecurso(resources, branches)
    return senas.map((s) => ({
      ...s,
      cliente: clients.find((c) => c.id === s.client_id)?.name ?? s.client_id ?? '—',
      servicio: services.find((v) => v.id === s.service_id)?.name ?? s.service_id ?? '—',
      local: s.appointment_starts_at
        ? enHoraDePared(s.appointment_starts_at, (s.resource_id && zonas[s.resource_id]) || 'UTC')
        : null,
    }))
  }, [senas, clients, services, resources, branches])

  const totalPendiente = useMemo(
    () => filas.filter((f) => f.status === 'pending').reduce((t, f) => t + Number(f.amount), 0),
    [filas],
  )

  async function transicion(sena: SenaConTurno, accion: 'refund' | 'mark-failed') {
    setConfirmando(null)
    setErrorAccion(null)
    try {
      await api.post(`/deposits/${sena.id}/${accion}`)
      await cargar()
    } catch (err) {
      setErrorAccion(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  const columns = useMemo<ColumnDef<Fila>[]>(() => [
    {
      id: 'turno',
      accessorFn: (f) => f.local ?? '',
      header: sortableHeader('Turno'),
      size: 150,
      minSize: 130,
      // El link lleva al turno en la agenda, parado en su día: desde ahí se
      // ve el resto (el recurso, el estado) y se lo reprograma si hace falta.
      cell: ({ row }) => row.original.local
        ? (
          <Link
            className="underline-offset-4 hover:underline"
            to={`/agenda?dia=${row.original.local.slice(0, 10)}&turno=${row.original.appointment_id}`}
          >
            {fechaHora(row.original.local)}
          </Link>
        )
        : '—',
    },
    {
      accessorKey: 'cliente', header: sortableHeader('Cliente'), size: 180, minSize: 120,
      meta: { stretch: true },
      cell: ({ row }) => <span className="block truncate font-medium" title={row.original.cliente}>{row.original.cliente}</span>,
    },
    {
      accessorKey: 'servicio', header: 'Servicio', size: 150, minSize: 110,
      cell: ({ row }) => <span className="block truncate" title={row.original.servicio}>{row.original.servicio}</span>,
    },
    {
      id: 'monto',
      accessorFn: (f) => Number(f.amount),
      header: () => <div className="text-right">Monto</div>,
      size: 120,
      minSize: 100,
      cell: ({ row }) => <div className="text-right tabular-nums">{formatMonto(row.original.amount)}</div>,
    },
    {
      accessorKey: 'status', header: 'Estado', size: 110, minSize: 95,
      cell: ({ row }) => <BadgeSena estado={row.original.status} />,
    },
    {
      id: 'medio', header: 'Medio de pago', size: 140, minSize: 110,
      cell: ({ row }) => nombreMedio(medios, row.original.medio_pago),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => {
        const s = row.original
        return (
          <div className="flex justify-end gap-1">
            {s.status === 'pending' && (
              <>
                <Button
                  size="sm" variant="outline"
                  aria-label={`Marcar fallida la seña de ${s.cliente}`}
                  onClick={() => setConfirmando({ sena: s, accion: 'mark-failed' })}
                >
                  Fallida
                </Button>
                <Button
                  size="sm"
                  aria-label={`Cobrar la seña de ${s.cliente}`}
                  onClick={() => setCobrando(s)}
                >
                  Cobrar
                </Button>
              </>
            )}
            {s.status === 'paid' && (
              <Button
                size="sm" variant="outline"
                aria-label={`Devolver la seña de ${s.cliente}`}
                onClick={() => setConfirmando({ sena: s, accion: 'refund' })}
              >
                Devolver
              </Button>
            )}
          </div>
        )
      },
    },
  ], [medios])

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <TituloPantalla icono={HandCoins}>Señas</TituloPantalla>
          <p className="text-sm text-muted-foreground">
            Las señas se piden desde el turno, en la Agenda. Acá se cobran y se
            devuelven.
          </p>
        </div>
        {/* Controlado por la URL, como la vista de la agenda: con
            `defaultValue`, entrar con `?estado=paid` pintaría la primera
            pestaña y mostraría otra cosa. */}
        <Tabs value={filtro} onValueChange={(v) => setParams({ estado: v })}>
          <TabsList aria-label="Estado de las señas">
            {FILTROS.map((f) => (
              <TabsTrigger key={f.valor} value={f.valor}>{f.label}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {errorAccion && <p className="text-sm text-destructive">{errorAccion}</p>}

      {!cargando && !error && (filtro === 'pending' || filtro === TODAS) && totalPendiente > 0 && (
        <p className="text-sm">
          Pendiente de cobro: <span className="font-semibold">{formatMonto(totalPendiente)}</span>
        </p>
      )}

      <Card>
        <CardContent>
          {cargando ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={filas}
              emptyMessage={filtro === TODAS
                ? 'Todavía no se pidió ninguna seña.'
                : `No hay señas ${SENA_LABELS[filtro].toLowerCase()}s.`}
              search={{
                campos: (f) => [f.cliente, f.servicio],
                placeholder: 'Buscar por cliente o servicio',
                ariaLabel: 'Buscar seña',
              }}
            />
          )}
        </CardContent>
      </Card>

      <CobrarSenaDialog
        sena={cobrando}
        medios={medios}
        onClose={() => setCobrando(null)}
        onCobrada={async () => { setCobrando(null); await cargar() }}
      />
      <ConfirmDialog
        open={confirmando !== null}
        onOpenChange={(abierto) => { if (!abierto) setConfirmando(null) }}
        title={confirmando?.accion === 'refund' ? '¿Devolver la seña?' : '¿Marcar la seña como fallida?'}
        description={confirmando?.accion === 'refund'
          ? `Se registra la devolución de ${formatMonto(confirmando.sena.amount)} a ${confirmando.sena.cliente}. No se puede deshacer.`
          : 'La seña queda como no cobrada y ya no se puede cobrar. No se puede deshacer.'}
        confirmLabel={confirmando?.accion === 'refund' ? 'Devolver' : 'Marcar fallida'}
        onConfirm={() => confirmando && transicion(confirmando.sena, confirmando.accion)}
      />
    </div>
  )
}

import { useEffect, useState, type FormEvent } from 'react'
import {
  api, ApiError, STATUS_LABELS,
  type Appointment, type AppointmentStatus, type Client, type Resource, type Service,
} from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('es-AR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

const STATUS_BADGE_VARIANT: Record<AppointmentStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'outline',
  confirmed: 'secondary',
  in_progress: 'secondary',
  completed: 'default',
  cancelled: 'destructive',
  no_show: 'destructive',
}

export function Agenda() {
  const [resources, setResources] = useState<Resource[]>([])
  const [services, setServices] = useState<Service[]>([])
  const [clients, setClients] = useState<Client[]>([])
  const [resourceId, setResourceId] = useState<string>('')
  const [dateFrom, setDateFrom] = useState(todayIso())
  const [dateTo, setDateTo] = useState(todayIso())
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const [newService, setNewService] = useState('')
  const [newClient, setNewClient] = useState('')
  const [newStartsAt, setNewStartsAt] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    Promise.all([
      api.get<Resource[]>('/resources'),
      api.get<Service[]>('/services'),
      api.get<Client[]>('/clients'),
    ]).then(([r, s, c]) => {
      setResources(r)
      setServices(s)
      setClients(c)
      if (r.length > 0) setResourceId(r[0].id)
    }).catch((err) => setError(describeError(err)))
  }, [])

  useEffect(() => {
    if (!resourceId) return
    loadAgenda()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceId, dateFrom, dateTo])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function loadAgenda() {
    setLoading(true)
    setError(null)
    try {
      const items = await api.get<Appointment[]>(
        `/resources/${resourceId}/agenda?date_from=${dateFrom}&date_to=${dateTo}`,
      )
      setAppointments(items.sort((a, b) => a.starts_at.localeCompare(b.starts_at)))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    if (!newService || !newClient || !newStartsAt) return
    setCreating(true)
    setError(null)
    try {
      await api.post('/appointments', {
        resource_id: resourceId,
        service_id: newService,
        client_id: newClient,
        starts_at: newStartsAt,
      })
      setNewStartsAt('')
      await loadAgenda()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setCreating(false)
    }
  }

  async function handleAction(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      await loadAgenda()
    } catch (err) {
      setError(describeError(err))
    }
  }

  function clientName(id: string): string {
    return clients.find((c) => c.id === id)?.name ?? id
  }

  function serviceName(id: string): string {
    return services.find((s) => s.id === id)?.name ?? id
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="grid gap-1.5">
          <Label>Recurso</Label>
          <Select value={resourceId} onValueChange={setResourceId}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Recurso…" />
            </SelectTrigger>
            <SelectContent>
              {resources.map((r) => (
                <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="date-from">Desde</Label>
          <Input id="date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="date-to">Hasta</Label>
          <Input id="date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Nuevo turno</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-wrap items-end gap-3" onSubmit={handleCreate}>
            <div className="grid gap-1.5">
              <Label>Servicio</Label>
              <Select value={newService} onValueChange={setNewService}>
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="Servicio…" />
                </SelectTrigger>
                <SelectContent>
                  {services.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.name} ({s.duration_minutes} min)</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>Cliente</Label>
              <Select value={newClient} onValueChange={setNewClient}>
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="Cliente…" />
                </SelectTrigger>
                <SelectContent>
                  {clients.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="starts-at">Horario</Label>
              <Input
                id="starts-at"
                type="datetime-local"
                value={newStartsAt}
                onChange={(e) => setNewStartsAt(e.target.value)}
                required
                className="w-56"
              />
            </div>
            <Button type="submit" disabled={creating || !resourceId}>
              {creating ? 'Creando…' : 'Crear turno'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : appointments.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Sin turnos en el rango seleccionado.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Horario</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Servicio</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {appointments.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell>{formatTime(a.starts_at)}</TableCell>
                    <TableCell>{clientName(a.client_id)}</TableCell>
                    <TableCell>{serviceName(a.service_id)}</TableCell>
                    <TableCell>
                      <Badge variant={STATUS_BADGE_VARIANT[a.status]}>{STATUS_LABELS[a.status]}</Badge>
                    </TableCell>
                    <TableCell className="flex flex-wrap justify-end gap-2">
                      {a.status === 'pending' && (
                        <Button size="sm" variant="outline" onClick={() => handleAction(() => api.post(`/appointments/${a.id}/confirm`))}>
                          Confirmar
                        </Button>
                      )}
                      {(a.status === 'pending' || a.status === 'confirmed') && (
                        <Button size="sm" variant="outline" onClick={() => handleAction(() => api.post(`/appointments/${a.id}/cancel`))}>
                          Cancelar
                        </Button>
                      )}
                      {a.status === 'confirmed' && (
                        <Button size="sm" variant="outline" onClick={() => handleAction(() => api.post(`/appointments/${a.id}/complete`))}>
                          Completar
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type Appointment, type Client, type Resource, type Service } from '../api'
import { useAuth } from '../context/AuthContext'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('es-AR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente',
  confirmed: 'Confirmado',
  in_progress: 'En curso',
  completed: 'Completado',
  cancelled: 'Cancelado',
  no_show: 'No se presentó',
}

export function Agenda() {
  const { user, logout } = useAuth()

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
    <div className="agenda-page">
      <header className="agenda-header">
        <h1>Gestiolibra — Agenda</h1>
        <div className="user-info">
          <span>{user?.name} ({user?.role})</span>
          <button onClick={() => logout()}>Salir</button>
        </div>
      </header>

      <section className="filters">
        <label>
          Recurso
          <select value={resourceId} onChange={(e) => setResourceId(e.target.value)}>
            {resources.map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        </label>
        <label>
          Desde
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label>
          Hasta
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>
      </section>

      {error && <p className="error">{error}</p>}

      <section className="new-appointment">
        <h2>Nuevo turno</h2>
        <form onSubmit={handleCreate}>
          <select value={newService} onChange={(e) => setNewService(e.target.value)} required>
            <option value="" disabled>Servicio…</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>{s.name} ({s.duration_minutes} min)</option>
            ))}
          </select>
          <select value={newClient} onChange={(e) => setNewClient(e.target.value)} required>
            <option value="" disabled>Cliente…</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <input
            type="datetime-local"
            value={newStartsAt}
            onChange={(e) => setNewStartsAt(e.target.value)}
            required
          />
          <button type="submit" disabled={creating || !resourceId}>
            {creating ? 'Creando…' : 'Crear turno'}
          </button>
        </form>
      </section>

      <section className="appointments">
        {loading ? (
          <p>Cargando…</p>
        ) : appointments.length === 0 ? (
          <p>Sin turnos en el rango seleccionado.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Horario</th>
                <th>Cliente</th>
                <th>Servicio</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {appointments.map((a) => (
                <tr key={a.id}>
                  <td>{formatTime(a.starts_at)}</td>
                  <td>{clientName(a.client_id)}</td>
                  <td>{serviceName(a.service_id)}</td>
                  <td>{STATUS_LABELS[a.status] ?? a.status}</td>
                  <td className="actions">
                    {a.status === 'pending' && (
                      <button onClick={() => handleAction(() => api.post(`/appointments/${a.id}/confirm`))}>
                        Confirmar
                      </button>
                    )}
                    {(a.status === 'pending' || a.status === 'confirmed') && (
                      <button onClick={() => handleAction(() => api.post(`/appointments/${a.id}/cancel`))}>
                        Cancelar
                      </button>
                    )}
                    {a.status === 'confirmed' && (
                      <button onClick={() => handleAction(() => api.post(`/appointments/${a.id}/complete`))}>
                        Completar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { api, ApiError, STATUS_LABELS, type DashboardSummary } from '../api'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' }).format(value)
}

export function Dashboard() {
  const [dateFrom, setDateFrom] = useState(todayIso())
  const [dateTo, setDateTo] = useState(todayIso())
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadSummary()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo])

  async function loadSummary() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<DashboardSummary>(
        `/dashboard?date_from=${dateFrom}&date_to=${dateTo}`,
      )
      setSummary(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError('No tenés acceso al dashboard (requiere rol admin y el módulo "dashboard" habilitado en el plan).')
      } else {
        setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      }
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <h2>Dashboard</h2>
      </div>

      <section className="filters">
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
      {loading && <p>Cargando…</p>}

      {summary && (
        <div className="dashboard-cards">
          <article className="card">
            <h3>Turnos</h3>
            <p className="big-number">{summary.turnos.total_en_periodo}</p>
            <p className="muted">en el rango — {summary.turnos.hoy} hoy</p>
            <ul>
              {Object.entries(summary.turnos.por_estado)
                .filter(([, count]) => count > 0)
                .map(([status, count]) => (
                  <li key={status}>
                    {STATUS_LABELS[status as keyof typeof STATUS_LABELS] ?? status}: {count}
                  </li>
                ))}
            </ul>
          </article>

          <article className="card">
            <h3>Clientes</h3>
            <p className="big-number">{summary.clientes.total_activos}</p>
            <p className="muted">activos — {summary.clientes.nuevos_en_periodo} nuevos en el rango</p>
          </article>

          <article className="card">
            <h3>Recordatorios y señas</h3>
            <p>{summary.recordatorios_enviados_en_periodo} recordatorios enviados en el rango</p>
            <p>{summary.senas_pendientes} señas pendientes</p>
          </article>

          <article className="card">
            <h3>Facturación</h3>
            <p className="big-number">{summary.facturacion.facturas_emitidas_en_periodo}</p>
            <p className="muted">facturas emitidas en el rango</p>
            <ul>
              <li>Ingresos del período: {formatCurrency(summary.facturacion.caja.ingresos_en_periodo)}</li>
              <li>Egresos del período: {formatCurrency(summary.facturacion.caja.egresos_en_periodo)}</li>
              <li>Saldo del período: {formatCurrency(summary.facturacion.caja.saldo_periodo)}</li>
              <li>Saldo total: {formatCurrency(summary.facturacion.caja.saldo_total)}</li>
            </ul>
          </article>
        </div>
      )}
    </div>
  )
}

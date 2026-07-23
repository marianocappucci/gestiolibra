import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type Client } from '../api'
import { useAuth } from '../context/AuthContext'

const CONDICIONES_IVA = [
  'Responsable Inscripto',
  'Monotributista',
  'IVA Exento',
  'Consumidor Final',
  'No Alcanzado',
]

type FormState = {
  id: string
  name: string
  phone: string
  email: string
  cuit: string
  condicion_iva: string
}

const EMPTY_FORM: FormState = { id: '', name: '', phone: '', email: '', cuit: '', condicion_iva: '' }

export function Clientes() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [clients, setClients] = useState<Client[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadClients()
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function loadClients() {
    setLoading(true)
    setError(null)
    try {
      const items = await api.get<Client[]>('/clients')
      setClients(items.sort((a, b) => a.name.localeCompare(b.name)))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  function startCreate() {
    setEditingId('new')
    setForm(EMPTY_FORM)
  }

  function startEdit(client: Client) {
    setEditingId(client.id)
    setForm({
      id: client.id,
      name: client.name,
      phone: client.phone ?? '',
      email: client.email ?? '',
      cuit: client.cuit ?? '',
      condicion_iva: client.condicion_iva ?? '',
    })
  }

  function cancelEdit() {
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    const payload = {
      name: form.name,
      phone: form.phone || null,
      email: form.email || null,
      cuit: form.cuit || null,
      condicion_iva: form.condicion_iva || null,
    }
    try {
      if (editingId === 'new') {
        await api.post('/clients', { id: form.id, ...payload })
      } else if (editingId) {
        await api.put(`/clients/${editingId}`, payload)
      }
      cancelEdit()
      await loadClients()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(client: Client) {
    setError(null)
    try {
      await api.del(`/clients/${client.id}`)
      await loadClients()
    } catch (err) {
      setError(describeError(err))
    }
  }

  return (
    <div className="clientes-page">
      <div className="page-header">
        <h2>Clientes</h2>
        {isAdmin && editingId === null && (
          <button onClick={startCreate}>+ Nuevo cliente</button>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {isAdmin && editingId !== null && (
        <form className="client-form" onSubmit={handleSubmit}>
          {editingId === 'new' && (
            <input
              placeholder="ID"
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value })}
              required
            />
          )}
          <input
            placeholder="Nombre"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <input
            placeholder="Teléfono"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          <input
            placeholder="Email"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <input
            placeholder="CUIT"
            value={form.cuit}
            onChange={(e) => setForm({ ...form, cuit: e.target.value })}
          />
          <select
            value={form.condicion_iva}
            onChange={(e) => setForm({ ...form, condicion_iva: e.target.value })}
          >
            <option value="">Condición de IVA…</option>
            {CONDICIONES_IVA.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button type="submit" disabled={saving}>
            {saving ? 'Guardando…' : editingId === 'new' ? 'Crear' : 'Guardar'}
          </button>
          <button type="button" onClick={cancelEdit}>Cancelar</button>
        </form>
      )}

      {loading ? (
        <p>Cargando…</p>
      ) : clients.length === 0 ? (
        <p>Sin clientes todavía.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Teléfono</th>
              <th>Email</th>
              <th>CUIT</th>
              <th>Condición IVA</th>
              <th>Estado</th>
              {isAdmin && <th>Acciones</th>}
            </tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.phone ?? '—'}</td>
                <td>{c.email ?? '—'}</td>
                <td>{c.cuit ?? '—'}</td>
                <td>{c.condicion_iva ?? '—'}</td>
                <td>{c.active ? 'Activo' : 'Inactivo'}</td>
                {isAdmin && (
                  <td className="actions">
                    <button onClick={() => startEdit(c)}>Editar</button>
                    <button onClick={() => handleDelete(c)}>Eliminar</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

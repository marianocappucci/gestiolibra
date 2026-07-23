import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type Client } from '../api'
import { useAuth } from '../context/AuthContext'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

const CONDICIONES_IVA = [
  'Responsable Inscripto',
  'Monotributista',
  'IVA Exento',
  'Consumidor Final',
  'No Alcanzado',
]

type FormState = {
  name: string
  phone: string
  email: string
  cuit: string
  condicion_iva: string
}

const EMPTY_FORM: FormState = { name: '', phone: '', email: '', cuit: '', condicion_iva: '' }

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
        await api.post('/clients', payload)
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
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Clientes</h2>
        {isAdmin && editingId === null && (
          <Button onClick={startCreate}>+ Nuevo cliente</Button>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {isAdmin && editingId !== null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{editingId === 'new' ? 'Nuevo cliente' : 'Editar cliente'}</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="flex flex-wrap items-end gap-3" onSubmit={handleSubmit}>
              <Input
                placeholder="Nombre"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                className="w-48"
              />
              <Input
                placeholder="Teléfono"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="w-40"
              />
              <Input
                placeholder="Email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-52"
              />
              <Input
                placeholder="CUIT"
                value={form.cuit}
                onChange={(e) => setForm({ ...form, cuit: e.target.value })}
                className="w-36"
              />
              <Select
                value={form.condicion_iva}
                onValueChange={(value) => setForm({ ...form, condicion_iva: value })}
              >
                <SelectTrigger className="w-52">
                  <SelectValue placeholder="Condición de IVA…" />
                </SelectTrigger>
                <SelectContent>
                  {CONDICIONES_IVA.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
              <Button type="submit" disabled={saving}>
                {saving ? 'Guardando…' : editingId === 'new' ? 'Crear' : 'Guardar'}
              </Button>
              <Button type="button" variant="outline" onClick={cancelEdit}>Cancelar</Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : clients.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Sin clientes todavía.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Teléfono</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>CUIT</TableHead>
                  <TableHead>Condición IVA</TableHead>
                  <TableHead>Estado</TableHead>
                  {isAdmin && <TableHead className="text-right">Acciones</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {clients.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium">{c.name}</TableCell>
                    <TableCell>{c.phone ?? '—'}</TableCell>
                    <TableCell>{c.email ?? '—'}</TableCell>
                    <TableCell>{c.cuit ?? '—'}</TableCell>
                    <TableCell>{c.condicion_iva ?? '—'}</TableCell>
                    <TableCell>
                      <Badge variant={c.active ? 'default' : 'outline'}>
                        {c.active ? 'Activo' : 'Inactivo'}
                      </Badge>
                    </TableCell>
                    {isAdmin && (
                      <TableCell className="flex justify-end gap-2">
                        <Button size="sm" variant="outline" onClick={() => startEdit(c)}>Editar</Button>
                        <Button size="sm" variant="outline" onClick={() => handleDelete(c)}>Eliminar</Button>
                      </TableCell>
                    )}
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

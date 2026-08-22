import { useEffect, useMemo, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { api, ApiError, type Client } from '../api'
import { useAuth } from '../context/AuthContext'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BadgeEstado } from 'libra-ui/badge-estado'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Pencil, Trash2, Users } from 'lucide-react'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

const CONDICIONES_IVA = [
  'Responsable Inscripto',
  'Monotributista',
  'IVA Exento',
  'Consumidor Final',
  'No Alcanzado',
]

const clientSchema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio'),
  phone: z.string().trim().optional(),
  email: z.string().trim().email('Email inválido').optional().or(z.literal('')),
  cuit: z.string().trim().optional(),
  condicion_iva: z.string().optional(),
})

type ClientFormValues = z.infer<typeof clientSchema>

const EMPTY_VALUES: ClientFormValues = { name: '', phone: '', email: '', cuit: '', condicion_iva: '' }

export function Clientes() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [clients, setClients] = useState<Client[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const form = useForm<ClientFormValues>({
    resolver: zodResolver(clientSchema),
    defaultValues: EMPTY_VALUES,
  })

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
    form.reset(EMPTY_VALUES)
  }

  function startEdit(client: Client) {
    setEditingId(client.id)
    form.reset({
      name: client.name,
      phone: client.phone ?? '',
      email: client.email ?? '',
      cuit: client.cuit ?? '',
      condicion_iva: client.condicion_iva ?? '',
    })
  }

  function cancelEdit() {
    setEditingId(null)
    form.reset(EMPTY_VALUES)
  }

  async function handleSubmit(values: ClientFormValues) {
    setSaving(true)
    setError(null)
    const payload = {
      name: values.name,
      phone: values.phone || null,
      email: values.email || null,
      cuit: values.cuit || null,
      condicion_iva: values.condicion_iva || null,
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

  // Anchos fijos al contenido real de cada columna + la de nombre elastica,
  // mismo patron que Contalibra/Restolibra: la tabla llena el ancho
  // disponible sin desbordarlo. La columna de acciones no declara ancho --
  // la mide `libra-ui` sola (ver wiki/entities/libra-ui.md v0.4.0).
  const columns = useMemo<ColumnDef<Client>[]>(() => {
    const base: ColumnDef<Client>[] = [
      { accessorKey: 'name', header: sortableHeader('Nombre'), size: 200, minSize: 120, meta: { stretch: true }, cell: ({ row }) => <span className="block truncate font-medium" title={row.original.name}>{row.original.name}</span> },
      { accessorKey: 'phone', header: 'Teléfono', size: 130, minSize: 100, cell: ({ row }) => row.original.phone ?? '—' },
      { accessorKey: 'email', header: 'Email', size: 200, minSize: 140, cell: ({ row }) => <span className="block truncate" title={row.original.email ?? undefined}>{row.original.email ?? '—'}</span> },
      { accessorKey: 'cuit', header: 'CUIT', size: 130, minSize: 110, cell: ({ row }) => row.original.cuit ?? '—' },
      { accessorKey: 'condicion_iva', header: 'Condición IVA', size: 150, minSize: 120, cell: ({ row }) => <span className="block truncate" title={row.original.condicion_iva ?? undefined}>{row.original.condicion_iva ?? '—'}</span> },
      {
        accessorKey: 'active',
        header: 'Estado',
        size: 100,
        minSize: 85,
        cell: ({ row }) => (
          <BadgeEstado tono={row.original.active ? 'ok' : 'neutro'}>
            {row.original.active ? 'Activo' : 'Inactivo'}
          </BadgeEstado>
        ),
      },
    ]
    if (isAdmin) {
      base.push({
        id: 'actions',
        header: () => <div className="text-right">Acciones</div>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button size="icon" variant="outline" title="Editar cliente" aria-label="Editar cliente" onClick={() => startEdit(row.original)}><Pencil /></Button>
            <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" title="Eliminar cliente" aria-label="Eliminar cliente" onClick={() => handleDelete(row.original)}><Trash2 /></Button>
          </div>
        ),
      })
    }
    return base
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin])

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <TituloPantalla icono={Users}>Clientes</TituloPantalla>
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
            <Form {...form}>
              <form className="flex flex-wrap items-start gap-3" onSubmit={form.handleSubmit(handleSubmit)}>
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Nombre</FormLabel>
                      <FormControl>
                        <Input {...field} className="w-48" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="phone"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Teléfono</FormLabel>
                      <FormControl>
                        <Input {...field} className="w-40" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Email</FormLabel>
                      <FormControl>
                        <Input type="email" {...field} className="w-52" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="cuit"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>CUIT</FormLabel>
                      <FormControl>
                        <Input {...field} className="w-36" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="condicion_iva"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Condición de IVA</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger className="w-52">
                            <SelectValue placeholder="Condición de IVA…" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {CONDICIONES_IVA.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="flex gap-2 pt-6">
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : editingId === 'new' ? 'Crear' : 'Guardar'}
                  </Button>
                  <Button type="button" variant="outline" onClick={cancelEdit}>Cancelar</Button>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable columns={columns} data={clients} emptyMessage="Sin clientes todavía." />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

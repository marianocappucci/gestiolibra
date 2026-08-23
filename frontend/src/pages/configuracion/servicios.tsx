/** Servicios: qué se ofrece, cuánto dura y cuánto sale en cada sucursal.
 *
 *  Los tres datos del pedido del humano —*"no se puede parametrizar servicios,
 *  horarios de esos servicios, honorarios de esos servicios"*— viven acá:
 *
 *  - **Qué se ofrece**: el nombre.
 *  - **Cuánto dura**: `duration_minutes`. **Es el "horario" del servicio**: no
 *    tiene una franja propia (esa es del recurso que lo presta), lo que tiene
 *    es cuánto ocupa. De ahí sale el alto del bloque en la agenda y el `hasta`
 *    del turno, y es lo que decide si entra en el hueco que queda.
 *  - **Cuánto sale**: el precio **por sucursal**, que es como lo modela el
 *    backend (`/services/{id}/prices`). Un servicio sin precio en la sucursal
 *    del turno se completa sin facturar; con precio, completar el turno emite
 *    la factura.
 */
import { useCallback, useEffect, useState } from 'react'
import { api, type Branch, type PrecioDeServicio, type Service } from '../../api'
import { Button } from '@/components/ui/button'
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  CampoActivo, ListaDelCatalogo, PieDeFormulario, comoIdentificador, describirError,
} from './catalogo'

const VACIO = { id: '', name: '', duration_minutes: '30', active: true }

function pesos(valor: string | number): string {
  return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' })
    .format(Number(valor))
}

export function ServiciosCard() {
  const [servicios, setServicios] = useState<Service[]>([])
  const [sucursales, setSucursales] = useState<Branch[]>([])
  const [elegido, setElegido] = useState<string | null>(null)
  const [form, setForm] = useState({ ...VACIO })
  const [editando, setEditando] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const [s, b] = await Promise.all([
        api.get<Service[]>('/services'),
        api.get<Branch[]>('/branches'),
      ])
      setServicios(Array.isArray(s) ? s : [])
      setSucursales(Array.isArray(b) ? b : [])
    } catch (err) {
      setError(describirError(err))
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => { void cargar() }, [cargar])

  function editar(id: string) {
    const s = servicios.find((x) => x.id === id)
    setElegido(id)
    setError(null)
    if (!s) return
    setEditando(true)
    setForm({
      id: s.id, name: s.name,
      duration_minutes: String(s.duration_minutes), active: s.active,
    })
  }

  function limpiar() {
    setEditando(false)
    setForm({ ...VACIO })
    setError(null)
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault()
    setGuardando(true)
    setError(null)
    const cuerpo = {
      name: form.name,
      duration_minutes: Number(form.duration_minutes),
      active: form.active,
    }
    try {
      if (editando) {
        await api.put(`/services/${form.id}`, cuerpo)
      } else {
        const id = form.id || comoIdentificador(form.name)
        await api.post('/services', { id, ...cuerpo })
        setElegido(id)
      }
      await cargar()
      if (!editando) limpiar()
    } catch (err) {
      setError(describirError(err))
    } finally {
      setGuardando(false)
    }
  }

  async function borrar() {
    setError(null)
    try {
      await api.del(`/services/${form.id}`)
      setElegido(null)
      limpiar()
      await cargar()
    } catch (err) {
      setError(describirError(err))
    }
  }

  return (
    <div className="grid gap-4">
      <ListaDelCatalogo
        titulo="Servicios"
        descripcion="Qué se ofrece y cuánto dura. La duración es lo que decide cuánto ocupa el turno en la agenda."
        items={servicios}
        elegido={elegido}
        onElegir={editar}
        nombre={(s) => s.name}
        detalleDeFila={(s) => `${s.duration_minutes} min`}
        vacio={cargando ? 'Cargando…' : 'Todavía no hay servicios. Creá el primero abajo.'}
        acciones={editando && <Button variant="outline" onClick={limpiar}>Nuevo servicio</Button>}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {editando ? `Editar «${form.name}»` : 'Nuevo servicio'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:max-w-2xl" onSubmit={guardar}>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="grid gap-1.5 md:col-span-2">
                <Label htmlFor="serv-nombre">Nombre</Label>
                <Input
                  id="serv-nombre" required value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="serv-dur">Duración (minutos)</Label>
                <Input
                  id="serv-dur" type="number" min={1} required
                  value={form.duration_minutes}
                  onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5 md:col-span-2">
                <Label htmlFor="serv-id">Identificador</Label>
                <Input
                  id="serv-id" disabled={editando}
                  placeholder={comoIdentificador(form.name) || 'corte'}
                  value={form.id}
                  onChange={(e) => setForm({ ...form, id: e.target.value })}
                />
              </div>
            </div>
            <CampoActivo
              id="serv-activo" checked={form.active}
              onChange={(v) => setForm({ ...form, active: v })}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <PieDeFormulario
              editando={editando} guardando={guardando}
              onCancelar={limpiar} onBorrar={borrar}
            />
          </form>
        </CardContent>
      </Card>

      {elegido && servicios.some((s) => s.id === elegido) && (
        <PreciosDelServicio
          key={elegido}
          serviceId={elegido}
          sucursales={sucursales}
        />
      )}
    </div>
  )
}

/** Los honorarios del servicio, uno por sucursal.
 *
 *  Se listan **todas** las sucursales y no sólo las que ya tienen precio: un
 *  servicio sin precio en una sucursal no factura al completarse, y eso es
 *  invisible si la sucursal directamente no aparece en la lista.
 */
function PreciosDelServicio({ serviceId, sucursales }: {
  serviceId: string
  sucursales: Branch[]
}) {
  const [precios, setPrecios] = useState<Record<string, string>>({})
  const [borrador, setBorrador] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const items = await api.get<PrecioDeServicio[]>(`/services/${serviceId}/prices`)
      const mapa = Object.fromEntries(
        (Array.isArray(items) ? items : []).map((p) => [p.branch_id, p.price]),
      )
      setPrecios(mapa)
      setBorrador(mapa)
    } catch (err) {
      setError(describirError(err))
    } finally {
      setCargando(false)
    }
  }, [serviceId])

  useEffect(() => { void cargar() }, [cargar])

  async function fijar(branchId: string) {
    setGuardando(branchId)
    setError(null)
    try {
      await api.put(`/services/${serviceId}/prices`, {
        branch_id: branchId, price: borrador[branchId] ?? '0',
      })
      await cargar()
    } catch (err) {
      setError(describirError(err))
    } finally {
      setGuardando(null)
    }
  }

  async function quitar(branchId: string) {
    setGuardando(branchId)
    setError(null)
    try {
      await api.del(`/services/${serviceId}/prices/${branchId}`)
      await cargar()
    } catch (err) {
      setError(describirError(err))
    } finally {
      setGuardando(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Honorarios por sucursal</CardTitle>
        <CardDescription>
          Cuánto se cobra este servicio en cada sucursal. Sin precio cargado, el
          turno se completa pero no emite factura.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        {cargando ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : sucursales.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No hay sucursales cargadas: el precio es por sucursal, así que primero
            hay que crear una.
          </p>
        ) : sucursales.map((s) => (
          <div key={s.id} className="flex flex-wrap items-end gap-2">
            <div className="grid flex-1 gap-1.5">
              <Label htmlFor={`precio-${s.id}`}>{s.name}</Label>
              <Input
                id={`precio-${s.id}`} type="number" min={0} step="0.01"
                className="w-40"
                placeholder="sin precio"
                value={borrador[s.id] ?? ''}
                onChange={(e) => setBorrador({ ...borrador, [s.id]: e.target.value })}
              />
            </div>
            <Button
              variant="outline" disabled={guardando === s.id || !borrador[s.id]}
              onClick={() => fijar(s.id)}
            >
              Guardar
            </Button>
            {precios[s.id] !== undefined && (
              <Button
                variant="ghost" className="text-destructive hover:text-destructive"
                disabled={guardando === s.id}
                onClick={() => quitar(s.id)}
              >
                Quitar
              </Button>
            )}
            <span className="pb-2 text-xs text-muted-foreground">
              {precios[s.id] !== undefined ? `Vigente: ${pesos(precios[s.id])}` : 'Sin precio'}
            </span>
          </div>
        ))}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}

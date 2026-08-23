/** Recursos: quién o qué atiende, y cuándo.
 *
 *  Un recurso es lo que se ocupa cuando se da un turno — una persona, un box,
 *  un sillón. Tres cosas cuelgan de él, y las tres deciden si un turno entra:
 *
 *  1. **Disponibilidad semanal**: su jornada, dentro del horario de la sucursal.
 *  2. **Bloqueos**: un rato puntual en el que no atiende (una reunión, una
 *     licencia de dos días).
 *  3. **Excepciones**: un día concreto que se cierra o se abre, y que **gana
 *     sobre la ventana semanal**. Es lo que permite abrir un domingo puntual o
 *     cerrar un feriado sin tocar la jornada.
 *
 *  🔴 **Un recurso sin ninguna ventana semanal no recibe turnos, nunca.** El
 *  motor no tiene con qué decir que sí, y toda alta vuelve con *"el recurso no
 *  está disponible en ese horario"*. Es distinto del horario de la sucursal,
 *  que es opt-in: cargar sólo ése deja la agenda muerta.
 */
import { useCallback, useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import {
  api, type Bloqueo, type Branch, type ExcepcionDeAgenda, type Resource,
} from '../../api'
import { Button } from '@/components/ui/button'
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { VentanasSemanales } from './ventanas'
import {
  CampoActivo, ListaDelCatalogo, PieDeFormulario, comoIdentificador, describirError,
} from './catalogo'

const SIN_SUCURSAL = '__ninguna__'
const VACIO = { id: '', name: '', branch_id: SIN_SUCURSAL, active: true }

export function RecursosCard() {
  const [recursos, setRecursos] = useState<Resource[]>([])
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
      const [r, b] = await Promise.all([
        api.get<Resource[]>('/resources'),
        api.get<Branch[]>('/branches'),
      ])
      setRecursos(Array.isArray(r) ? r : [])
      setSucursales(Array.isArray(b) ? b : [])
    } catch (err) {
      setError(describirError(err))
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => { void cargar() }, [cargar])

  function editar(id: string) {
    const r = recursos.find((x) => x.id === id)
    setElegido(id)
    setError(null)
    if (!r) return
    setEditando(true)
    setForm({
      id: r.id, name: r.name,
      branch_id: r.branch_id ?? SIN_SUCURSAL, active: r.active,
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
      name: form.name, active: form.active,
      branch_id: form.branch_id === SIN_SUCURSAL ? null : form.branch_id,
    }
    try {
      if (editando) {
        await api.put(`/resources/${form.id}`, cuerpo)
      } else {
        const id = form.id || comoIdentificador(form.name)
        await api.post('/resources', { id, ...cuerpo })
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
      await api.del(`/resources/${form.id}`)
      setElegido(null)
      limpiar()
      await cargar()
    } catch (err) {
      setError(describirError(err))
    }
  }

  const nombreSucursal = (id: string | null) =>
    (id && sucursales.find((s) => s.id === id)?.name) || 'sin sucursal'

  return (
    <div className="grid gap-4">
      <ListaDelCatalogo
        titulo="Recursos"
        descripcion="Quién o qué atiende. Un turno ocupa un recurso, y los choques se calculan sobre él."
        items={recursos}
        elegido={elegido}
        onElegir={editar}
        nombre={(r) => r.name}
        detalleDeFila={(r) => nombreSucursal(r.branch_id)}
        vacio={cargando ? 'Cargando…' : 'Todavía no hay recursos. Creá el primero abajo.'}
        acciones={editando && <Button variant="outline" onClick={limpiar}>Nuevo recurso</Button>}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {editando ? `Editar «${form.name}»` : 'Nuevo recurso'}
          </CardTitle>
          <CardDescription>
            Sin sucursal, el recurso se agenda en UTC y queda fuera del horario
            de atención: conviene asignarle una siempre.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:max-w-2xl" onSubmit={guardar}>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="rec-nombre">Nombre</Label>
                <Input
                  id="rec-nombre" required value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="rec-id">Identificador</Label>
                <Input
                  id="rec-id" disabled={editando}
                  placeholder={comoIdentificador(form.name) || 'box-1'}
                  value={form.id}
                  onChange={(e) => setForm({ ...form, id: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="rec-sucursal">Sucursal</Label>
                <Select
                  value={form.branch_id}
                  onValueChange={(v) => setForm({ ...form, branch_id: v })}
                >
                  <SelectTrigger id="rec-sucursal"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={SIN_SUCURSAL}>Sin sucursal</SelectItem>
                    {sucursales.map((s) => (
                      <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <CampoActivo
              id="rec-activo" checked={form.active}
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

      {elegido && recursos.some((r) => r.id === elegido) && (
        <>
          <VentanasSemanales
            key={`disp-${elegido}`}
            base={`/resources/${elegido}/availability`}
            titulo="Disponibilidad semanal"
            descripcion="La jornada de este recurso, dentro del horario de la sucursal."
            aviso="🔴 Sin disponibilidad este recurso NO recibe ningún turno: toda alta se rechaza."
          />
          <Bloqueos key={`blo-${elegido}`} resourceId={elegido} />
          <Excepciones key={`exc-${elegido}`} resourceId={elegido} />
        </>
      )}
    </div>
  )
}

/** Los ratos puntuales en los que el recurso no atiende.
 *
 *  ⚠️ Se cargan en **hora de pared de la sucursal** —igual que un turno— y el
 *  backend los convierte a instante al guardarlos (ADR-030). Vuelven en UTC,
 *  así que se muestran tal como los devuelve la API con su `Z`: convertirlos de
 *  nuevo acá sería una segunda fuente de verdad para la misma cuenta.
 */
function Bloqueos({ resourceId }: { resourceId: string }) {
  const [items, setItems] = useState<Bloqueo[]>([])
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const datos = await api.get<Bloqueo[]>(`/resources/${resourceId}/blocks`)
      setItems((Array.isArray(datos) ? datos : []).slice().sort(
        (a, b) => a.starts_at.localeCompare(b.starts_at),
      ))
    } catch (err) {
      setError(describirError(err))
    }
  }, [resourceId])

  useEffect(() => { void cargar() }, [cargar])

  async function agregar() {
    setGuardando(true)
    setError(null)
    try {
      await api.post(`/resources/${resourceId}/blocks`, {
        starts_at: desde, ends_at: hasta, reason: motivo,
      })
      setMotivo('')
      await cargar()
    } catch (err) {
      setError(describirError(err))
    } finally {
      setGuardando(false)
    }
  }

  async function borrar(id: number) {
    setError(null)
    try {
      await api.del(`/resources/${resourceId}/blocks/${id}`)
      await cargar()
    } catch (err) {
      setError(describirError(err))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Bloqueos</CardTitle>
        <CardDescription>
          Ratos puntuales en los que este recurso no atiende, aunque su jornada
          diga que sí. Se cargan en hora de la sucursal.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin bloqueos.</p>
        ) : (
          <ul className="grid gap-1 text-sm">
            {items.map((b) => (
              <li key={b.id} className="flex items-center gap-3">
                <span className="tabular-nums">
                  {b.starts_at.slice(0, 16).replace('T', ' ')} → {b.ends_at.slice(0, 16).replace('T', ' ')}
                </span>
                <span className="text-muted-foreground">{b.reason}</span>
                <Button
                  size="icon" variant="ghost"
                  className="size-7 text-destructive hover:text-destructive"
                  aria-label={`Borrar bloqueo ${b.starts_at}`}
                  onClick={() => borrar(b.id)}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-end gap-2 border-t pt-3">
          <div className="grid gap-1.5">
            <Label htmlFor={`blo-desde-${resourceId}`}>Desde</Label>
            <Input
              id={`blo-desde-${resourceId}`} type="datetime-local"
              value={desde} onChange={(e) => setDesde(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`blo-hasta-${resourceId}`}>Hasta</Label>
            <Input
              id={`blo-hasta-${resourceId}`} type="datetime-local"
              value={hasta} onChange={(e) => setHasta(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`blo-motivo-${resourceId}`}>Motivo</Label>
            <Input
              id={`blo-motivo-${resourceId}`} className="w-48"
              value={motivo} onChange={(e) => setMotivo(e.target.value)}
            />
          </div>
          <Button onClick={agregar} disabled={guardando || !desde || !hasta}>
            Agregar bloqueo
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}

/** Los días concretos que se cierran o se abren.
 *
 *  🔴 **Una excepción siempre gana sobre la ventana semanal**, en las dos
 *  direcciones: cierra un día que la jornada abría (un feriado) y abre uno que
 *  la jornada cerraba (un domingo puntual). Por eso el formulario pide
 *  explícitamente cuál de las dos cosas es, en vez de asumir que toda excepción
 *  es un cierre.
 */
function Excepciones({ resourceId }: { resourceId: string }) {
  const [items, setItems] = useState<ExcepcionDeAgenda[]>([])
  const [dia, setDia] = useState('')
  const [desde, setDesde] = useState('09:00')
  const [hasta, setHasta] = useState('19:00')
  const [abre, setAbre] = useState('cierra')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const datos = await api.get<ExcepcionDeAgenda[]>(`/resources/${resourceId}/exceptions`)
      setItems((Array.isArray(datos) ? datos : []).slice().sort(
        (a, b) => a.day.localeCompare(b.day),
      ))
    } catch (err) {
      setError(describirError(err))
    }
  }, [resourceId])

  useEffect(() => { void cargar() }, [cargar])

  async function agregar() {
    setGuardando(true)
    setError(null)
    try {
      await api.post(`/resources/${resourceId}/exceptions`, {
        day: dia, starts_at: `${desde}:00`, ends_at: `${hasta}:00`,
        available: abre === 'abre',
      })
      await cargar()
    } catch (err) {
      setError(describirError(err))
    } finally {
      setGuardando(false)
    }
  }

  async function borrar(id: number) {
    setError(null)
    try {
      await api.del(`/resources/${resourceId}/exceptions/${id}`)
      await cargar()
    } catch (err) {
      setError(describirError(err))
    }
  }

  /** `2026-08-22` → `22-08-2026`, el formato visible del ecosistema. */
  const fecha = (iso: string) => `${iso.slice(8, 10)}-${iso.slice(5, 7)}-${iso.slice(0, 4)}`

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Excepciones por fecha</CardTitle>
        <CardDescription>
          Un día concreto que se cierra (un feriado) o que se abre aunque la
          jornada no lo cubra (un domingo puntual). Le gana a la jornada.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin excepciones.</p>
        ) : (
          <ul className="grid gap-1 text-sm">
            {items.map((e) => (
              <li key={e.id} className="flex items-center gap-3">
                <span className="w-24 font-medium tabular-nums">{fecha(e.day)}</span>
                <span className="tabular-nums">
                  {e.starts_at.slice(0, 5)} – {e.ends_at.slice(0, 5)}
                </span>
                <span className={e.available ? 'text-emerald-600' : 'text-destructive'}>
                  {e.available ? 'abre' : 'cierra'}
                </span>
                <Button
                  size="icon" variant="ghost"
                  className="size-7 text-destructive hover:text-destructive"
                  aria-label={`Borrar excepción ${fecha(e.day)}`}
                  onClick={() => borrar(e.id)}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-end gap-2 border-t pt-3">
          <div className="grid gap-1.5">
            <Label htmlFor={`exc-dia-${resourceId}`}>Fecha</Label>
            <Input
              id={`exc-dia-${resourceId}`} type="date"
              value={dia} onChange={(e) => setDia(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`exc-desde-${resourceId}`}>Desde</Label>
            <Input
              id={`exc-desde-${resourceId}`} type="time" className="w-28"
              value={desde} onChange={(e) => setDesde(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`exc-hasta-${resourceId}`}>Hasta</Label>
            <Input
              id={`exc-hasta-${resourceId}`} type="time" className="w-28"
              value={hasta} onChange={(e) => setHasta(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`exc-tipo-${resourceId}`}>Qué hace</Label>
            <Select value={abre} onValueChange={setAbre}>
              <SelectTrigger id={`exc-tipo-${resourceId}`} className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="cierra">Cierra</SelectItem>
                <SelectItem value="abre">Abre</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button onClick={agregar} disabled={guardando || !dia}>Agregar excepción</Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}

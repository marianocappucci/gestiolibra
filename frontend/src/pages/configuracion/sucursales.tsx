/** Sucursales y su horario de atención.
 *
 *  Hasta el 2026-08-22 esto **no tenía pantalla**: los endpoints existían desde
 *  el MVP pero una sucursal sólo se podía dar de alta por API o por
 *  `scripts/seed_demo.py`. Un cliente nuevo no podía configurar su propio
 *  negocio, que es lo que el humano reportó.
 *
 *  ⚠️ **El huso no es un detalle administrativo.** Es lo que decide qué
 *  significa "las 17:00" en toda la agenda: el turno se guarda como instante y
 *  se valida contra el horario de atención en la hora de pared de ESTA
 *  sucursal (ADR-030). Una sucursal cargada en UTC muestra los turnos tres
 *  horas corridos.
 */
import { useCallback, useEffect, useState } from 'react'
import { api, type Branch } from '../../api'
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

/** Los husos que puede necesitar este producto.
 *
 *  Argentina primero y por defecto (regla de arranque de la familia). No es una
 *  lista de las 400 zonas IANA: son las que tienen sentido acá, y una lista
 *  corta se elige bien mientras que una larga se elige mal.
 */
const HUSOS = [
  ['America/Argentina/Buenos_Aires', 'Argentina (UTC-3)'],
  ['America/Argentina/Cordoba', 'Argentina · Córdoba (UTC-3)'],
  ['America/Argentina/Mendoza', 'Argentina · Mendoza (UTC-3)'],
  ['America/Montevideo', 'Uruguay (UTC-3)'],
  ['America/Santiago', 'Chile'],
  ['America/Asuncion', 'Paraguay'],
  ['UTC', 'UTC'],
] as const

const VACIA = {
  id: '', name: '', timezone: HUSOS[0][0] as string,
  phone: '', address: '', active: true,
}

export function SucursalesCard() {
  const [sucursales, setSucursales] = useState<Branch[]>([])
  const [elegida, setElegida] = useState<string | null>(null)
  const [form, setForm] = useState({ ...VACIA })
  const [editando, setEditando] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const items = await api.get<Branch[]>('/branches')
      setSucursales(Array.isArray(items) ? items : [])
    } catch (err) {
      setError(describirError(err))
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => { void cargar() }, [cargar])

  function editar(id: string) {
    const s = sucursales.find((x) => x.id === id)
    setElegida(id)
    setError(null)
    if (!s) return
    setEditando(true)
    setForm({
      id: s.id, name: s.name, timezone: s.timezone,
      phone: s.phone ?? '', address: s.address ?? '', active: s.active,
    })
  }

  function limpiar() {
    setEditando(false)
    setForm({ ...VACIA })
    setError(null)
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault()
    setGuardando(true)
    setError(null)
    const cuerpo = {
      name: form.name, active: form.active, timezone: form.timezone,
      phone: form.phone || null, address: form.address || null,
    }
    try {
      if (editando) {
        await api.put(`/branches/${form.id}`, cuerpo)
      } else {
        const id = form.id || comoIdentificador(form.name)
        await api.post('/branches', { id, ...cuerpo })
        setElegida(id)
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
      await api.del(`/branches/${form.id}`)
      setElegida(null)
      limpiar()
      await cargar()
    } catch (err) {
      setError(describirError(err))
    }
  }

  const nombreDelHuso = (tz: string) =>
    HUSOS.find(([valor]) => valor === tz)?.[1] ?? tz

  return (
    <div className="grid gap-4">
      <ListaDelCatalogo
        titulo="Sucursales"
        descripcion="Dónde se atiende. Cada recurso pertenece a una, y el huso de la sucursal es el que fija a qué hora del reloj corresponde cada turno."
        items={sucursales}
        elegido={elegida}
        onElegir={editar}
        nombre={(s) => s.name}
        detalleDeFila={(s) => [nombreDelHuso(s.timezone), s.address].filter(Boolean).join(' · ')}
        vacio={cargando ? 'Cargando…' : 'Todavía no hay sucursales. Creá la primera abajo.'}
        acciones={
          editando && (
            <Button variant="outline" onClick={limpiar}>Nueva sucursal</Button>
          )
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {editando ? `Editar «${form.name}»` : 'Nueva sucursal'}
          </CardTitle>
          <CardDescription>
            El identificador es la clave con la que quedan referenciados los
            recursos y los precios; se propone desde el nombre y no se puede
            cambiar después.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:max-w-2xl" onSubmit={guardar}>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="suc-nombre">Nombre</Label>
                <Input
                  id="suc-nombre" required value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="suc-id">Identificador</Label>
                <Input
                  id="suc-id" disabled={editando}
                  placeholder={comoIdentificador(form.name) || 'centro'}
                  value={form.id}
                  onChange={(e) => setForm({ ...form, id: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="suc-huso">Huso horario</Label>
                <Select
                  value={form.timezone}
                  onValueChange={(v) => setForm({ ...form, timezone: v })}
                >
                  <SelectTrigger id="suc-huso"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {HUSOS.map(([valor, etiqueta]) => (
                      <SelectItem key={valor} value={valor}>{etiqueta}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="suc-tel">Teléfono</Label>
                <Input
                  id="suc-tel" value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5 md:col-span-2">
                <Label htmlFor="suc-dir">Dirección</Label>
                <Input
                  id="suc-dir" value={form.address}
                  onChange={(e) => setForm({ ...form, address: e.target.value })}
                />
              </div>
            </div>
            <CampoActivo
              id="suc-activa" checked={form.active} etiqueta="Activa"
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

      {elegida && sucursales.some((s) => s.id === elegida) && (
        <VentanasSemanales
          key={elegida}
          base={`/branches/${elegida}/hours`}
          titulo="Horario de atención"
          descripcion="Cuándo abre el negocio en esta sucursal. Un turno fuera de esta franja se rechaza."
          aviso="Sin horarios, esta sucursal no restringe nada: el que manda es el horario de cada recurso."
        />
      )}
    </div>
  )
}

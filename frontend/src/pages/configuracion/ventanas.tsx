/** El editor de ventanas semanales, compartido por dos cosas que tienen la
 *  misma forma y significan distinto.
 *
 *  - **El horario de atención de una sucursal** (`/branches/{id}/hours`): a qué
 *    hora abre el negocio. Es **opt-in**: una sucursal sin horarios cargados no
 *    restringe nada.
 *  - **La disponibilidad de un recurso** (`/resources/{id}/availability`):
 *    cuándo atiende esa persona o ese box, **dentro** del horario del negocio.
 *
 *  🔴 **La asimetría entre las dos es la trampa del módulo, y por eso este
 *  componente la dice en pantalla.** Un recurso **sin ninguna ventana no recibe
 *  turnos nunca**: el motor no tiene con qué decir que sí, y cada alta vuelve
 *  con "el recurso no está disponible en ese horario". Cargar sólo el horario
 *  de la sucursal —que es lo intuitivo, porque es el dato que uno tiene— deja
 *  la agenda muerta sin ninguna pista de por qué.
 *
 *  ⚠️ Las horas son **hora de pared de la sucursal**, no del navegador: es la
 *  unidad en la que el backend las compara (ADR-030).
 */
import { useCallback, useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api, ApiError, DIAS_SEMANA, type VentanaSemanal } from '../../api'
import { Button } from '@/components/ui/button'
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

function describirError(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  return 'Error de conexión.'
}

/** `09:00:00` → `09:00`, que es lo que entiende un `<input type="time">`. */
function aHoraCorta(valor: string): string {
  return valor.slice(0, 5)
}

export function VentanasSemanales({ base, titulo, descripcion, aviso }: {
  /** El prefijo del recurso REST: `/branches/x/hours` o
   *  `/resources/x/availability`. Las dos rutas tienen el mismo contrato. */
  base: string
  titulo: string
  descripcion: string
  /** Lo que hay que saber antes de dejar esto vacío. */
  aviso?: string
}) {
  const [ventanas, setVentanas] = useState<VentanaSemanal[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dia, setDia] = useState('0')
  const [desde, setDesde] = useState('09:00')
  const [hasta, setHasta] = useState('19:00')
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    setCargando(true)
    setError(null)
    try {
      const items = await api.get<VentanaSemanal[]>(base)
      setVentanas((Array.isArray(items) ? items : []).slice().sort(
        (a, b) => a.weekday - b.weekday || a.starts_at.localeCompare(b.starts_at),
      ))
    } catch (err) {
      setError(describirError(err))
    } finally {
      setCargando(false)
    }
  }, [base])

  useEffect(() => { void cargar() }, [cargar])

  async function agregar() {
    setGuardando(true)
    setError(null)
    try {
      await api.post(base, {
        weekday: Number(dia), starts_at: `${desde}:00`, ends_at: `${hasta}:00`,
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
      await api.del(`${base}/${id}`)
      await cargar()
    } catch (err) {
      setError(describirError(err))
    }
  }

  /** Copia lo cargado para un día a los cinco días hábiles.
   *
   *  No es un adorno: sin esto, cargar "lunes a viernes de 9 a 19" son cinco
   *  altas idénticas a mano, por cada recurso y por cada sucursal. Es el gesto
   *  que más se repite en toda esta pantalla. */
  async function repetirEnLaSemana() {
    setGuardando(true)
    setError(null)
    try {
      const yaCargados = new Set(ventanas.map((v) => v.weekday))
      for (const d of [0, 1, 2, 3, 4]) {
        if (yaCargados.has(d)) continue
        await api.post(base, {
          weekday: d, starts_at: `${desde}:00`, ends_at: `${hasta}:00`,
        })
      }
      await cargar()
    } catch (err) {
      setError(describirError(err))
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{titulo}</CardTitle>
        <CardDescription>{descripcion}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {cargando ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : ventanas.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Sin horarios cargados.{aviso ? ` ${aviso}` : ''}
          </p>
        ) : (
          <ul className="grid gap-1 text-sm">
            {ventanas.map((v) => (
              <li key={v.id} className="flex items-center gap-3">
                <span className="w-24 font-medium">{DIAS_SEMANA[v.weekday]}</span>
                <span className="tabular-nums">
                  {aHoraCorta(v.starts_at)} – {aHoraCorta(v.ends_at)}
                </span>
                <Button
                  size="icon" variant="ghost"
                  className="size-7 text-destructive hover:text-destructive"
                  aria-label={`Borrar ${DIAS_SEMANA[v.weekday]} ${aHoraCorta(v.starts_at)}`}
                  onClick={() => borrar(v.id)}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-end gap-2 border-t pt-3">
          <div className="grid gap-1.5">
            <Label htmlFor={`${base}-dia`}>Día</Label>
            <Select value={dia} onValueChange={setDia}>
              <SelectTrigger id={`${base}-dia`} className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                {DIAS_SEMANA.map((d, i) => (
                  <SelectItem key={d} value={String(i)}>{d}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${base}-desde`}>Desde</Label>
            <Input
              id={`${base}-desde`} type="time" className="w-28"
              value={desde} onChange={(e) => setDesde(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${base}-hasta`}>Hasta</Label>
            <Input
              id={`${base}-hasta`} type="time" className="w-28"
              value={hasta} onChange={(e) => setHasta(e.target.value)}
            />
          </div>
          <Button onClick={agregar} disabled={guardando}>Agregar horario</Button>
          <Button variant="outline" onClick={repetirEnLaSemana} disabled={guardando}>
            Lunes a viernes
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}

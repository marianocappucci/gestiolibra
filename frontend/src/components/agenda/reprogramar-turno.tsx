/** Mover un turno a otro horario: `POST /appointments/{id}/reschedule`.
 *
 *  El endpoint existe desde el MVP y hasta el 2026-09-11 no tenía pantalla:
 *  para cambiar la hora de un turno había que cancelarlo y crear otro, que
 *  pierde el turno original —su historia, su seña— y deja un cancelado en la
 *  grilla que en realidad no fue una cancelación.
 *
 *  ⚠️ **Sólo cambia el horario, no el recurso.** El motor (`libragenda`)
 *  reprograma sobre el mismo recurso: `reschedule()` recibe el turno y el
 *  inicio nuevo, nada más. Pasar el turno a otro profesional sería otro caso de
 *  uso —con su propia validación de disponibilidad del recurso destino— y hoy
 *  no existe en el motor; no se simula acá con cancelar + crear.
 *
 *  **La validación es del backend y se muestra tal cual.** Choque con otro
 *  turno, fuera del horario de la sucursal o del recurso, un turno que ya no se
 *  puede mover: el backend contesta 409 con el motivo en castellano
 *  (`app/mensajes_agenda.py`) y el diálogo queda abierto con ese texto, para
 *  que quien atiende pruebe otra hora sin volver a cargar todo.
 */
import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { api, ApiError } from '../../api'
import { fechaHora } from '@/lib/fechas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import type { TurnoConRecurso } from './datos'

/** El inicio del turno como lo lee un `datetime-local`: `aaaa-mm-ddTHH:MM`,
 *  en la hora de pared de la sucursal que ya calculó `datos.ts`. */
function comoInput(turno: TurnoConRecurso): string {
  return turno.desde.slice(0, 16)
}

const reprogramarSchema = z.object({
  starts_at: z.string().min(1, 'Elegí el horario nuevo'),
  reason: z.string().trim().max(200, 'Hasta 200 caracteres').optional(),
})

type ReprogramarValues = z.infer<typeof reprogramarSchema>

export function ReprogramarTurnoDialog({
  turno, onClose, onReprogramado,
}: {
  turno: TurnoConRecurso | null
  onClose: () => void
  /** Recibe el día nuevo (`aaaa-mm-dd`, de la sucursal) para que la agenda
   *  vaya a mostrarlo: el turno movido al jueves no se ve parado en el lunes. */
  onReprogramado: (diaNuevo: string) => void | Promise<void>
}) {
  const [error, setError] = useState<string | null>(null)
  const form = useForm<ReprogramarValues>({
    resolver: zodResolver(reprogramarSchema),
    defaultValues: { starts_at: turno ? comoInput(turno) : '', reason: '' },
  })

  useEffect(() => {
    if (turno) {
      form.reset({ starts_at: comoInput(turno), reason: '' })
      setError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turno?.id])

  async function reprogramar(values: ReprogramarValues) {
    if (!turno) return
    setError(null)
    // Mandar el mismo horario no rompe nada —el motor lo acepta— pero deja una
    // transición "reprogramado" en la historia del turno sin que se haya
    // movido. Se frena acá, donde se ve por qué.
    //
    // 🔴 Acá y no como `refine` del schema: el schema se arma una vez, en el
    // primer render, cuando el diálogo todavía no tiene turno — el `refine`
    // compararía siempre contra el vacío y no frenaría nunca.
    if (values.starts_at === comoInput(turno)) {
      form.setError('starts_at', { message: 'Es el mismo horario que ya tiene' })
      return
    }
    try {
      await api.post(`/appointments/${turno.id}/reschedule`, {
        // Naive, sin huso, igual que el alta: el backend lo interpreta como
        // hora de pared de la sucursal del recurso (ADR-028). Mandarlo con
        // offset sería decidir acá algo que decide allá.
        starts_at: values.starts_at,
        // Vacío no se manda: el motor conserva el motivo anterior cuando no
        // llega uno nuevo, y un `""` lo pisaría con nada.
        ...(values.reason ? { reason: values.reason } : {}),
      })
      await onReprogramado(values.starts_at.slice(0, 10))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  return (
    <Dialog open={turno !== null} onOpenChange={(abierto) => { if (!abierto) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reprogramar turno</DialogTitle>
          <DialogDescription>
            {turno && <>Ahora: {fechaHora(turno.desde)} en {turno.recurso_nombre}. </>}
            El turno se mueve en el mismo recurso; el sistema revisa que el
            horario nuevo esté libre y dentro del horario de atención.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form className="grid gap-3" onSubmit={form.handleSubmit(reprogramar)}>
            <FormField
              control={form.control}
              name="starts_at"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Horario nuevo ({turno?.zona ?? 'UTC'})</FormLabel>
                  <FormControl>
                    <Input type="datetime-local" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Motivo (opcional)</FormLabel>
                  <FormControl>
                    <Input placeholder="Pidió otro horario…" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? 'Reprogramando…' : 'Reprogramar'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

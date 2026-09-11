/** La seña de un turno, dentro de su detalle en la agenda.
 *
 *  Es el lugar natural para pedirla: el cliente llama, se le da el turno y se
 *  le dice cuánto tiene que señar. El endpoint (`POST /appointments/{id}/deposit`)
 *  existía desde el MVP y no tenía pantalla.
 *
 *  **Quién hace qué** — lo decide el backend, acá sólo se refleja:
 *  - Pedir y ver la seña: admin y staff (es parte de dar el turno).
 *  - Cobrarla, marcarla fallida o devolverla: sólo admin (`/deposits/*`, que
 *    es plata que se mueve). Al staff no se le muestran esos botones; si los
 *    tocara, el backend le contestaría 403.
 *
 *  ⚠️ **Sin el módulo `senas` en el plan, la sección no aparece.** El backend
 *  contesta 403 a todo lo de señas; mostrar "no tenés acceso" adentro de cada
 *  turno sería ruido sobre una función que el cliente no contrató.
 */
import { useCallback, useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { api, ApiError, type MedioPago, type Sena } from '../../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { BadgeSena, CobrarSenaDialog } from '@/components/senas'
import { formatMonto, nombreMedio } from '@/lib/senas'
import type { TurnoConRecurso } from './datos'

/** Lo que se sabe de la seña del turno. `apagado` es el 403 del módulo. */
type Estado =
  | { tipo: 'cargando' }
  | { tipo: 'sin' }
  | { tipo: 'apagado' }
  | { tipo: 'error'; mensaje: string }
  | { tipo: 'sena'; sena: Sena }

const pedidoSchema = z.object({
  amount: z.string().trim()
    .min(1, 'Poné el monto')
    // Coma o punto: en Argentina se escribe `1500,50` y el backend espera
    // `1500.50`. Se normaliza al mandar; acá sólo se valida que sea un monto.
    .refine((v) => Number(v.replace(',', '.')) > 0, 'Tiene que ser un monto mayor a cero'),
})

type PedidoValues = z.infer<typeof pedidoSchema>

/** Los estados en que un turno todavía puede recibir una seña nueva: uno
 *  cancelado o ya atendido no tiene nada que señar. */
const ADMITE_SENA = new Set(['pending', 'confirmed'])

export function SenaDelTurno({
  turno, esAdmin, medios,
}: {
  turno: TurnoConRecurso
  esAdmin: boolean
  medios: MedioPago[]
}) {
  const [estado, setEstado] = useState<Estado>({ tipo: 'cargando' })
  const [errorAccion, setErrorAccion] = useState<string | null>(null)
  const [cobrando, setCobrando] = useState<Sena | null>(null)
  const [confirmando, setConfirmando] = useState<'devolver' | 'fallida' | null>(null)

  const form = useForm<PedidoValues>({
    resolver: zodResolver(pedidoSchema),
    defaultValues: { amount: '' },
  })

  const cargar = useCallback(async () => {
    try {
      const sena = await api.get<Sena>(`/appointments/${turno.id}/deposit`)
      // Sin `id` no es una seña, sea lo que sea que llegó: se trata como que no
      // hay, igual que el `Array.isArray` del catálogo de la agenda.
      setEstado(sena && typeof sena.id === 'string'
        ? { tipo: 'sena', sena } : { tipo: 'sin' })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setEstado({ tipo: 'sin' })
      else if (err instanceof ApiError && err.status === 403) setEstado({ tipo: 'apagado' })
      else setEstado({ tipo: 'error', mensaje: err instanceof ApiError ? err.detail : 'Error de conexión.' })
    }
  }, [turno.id])

  useEffect(() => {
    setEstado({ tipo: 'cargando' })
    setErrorAccion(null)
    form.reset({ amount: '' })
    void cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cargar])

  async function pedir(values: PedidoValues) {
    setErrorAccion(null)
    try {
      await api.post(`/appointments/${turno.id}/deposit`, {
        amount: values.amount.replace(',', '.'),
      })
      await cargar()
    } catch (err) {
      setErrorAccion(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  async function transicion(sena: Sena, accion: 'refund' | 'mark-failed') {
    setErrorAccion(null)
    setConfirmando(null)
    try {
      await api.post(`/deposits/${sena.id}/${accion}`)
      await cargar()
    } catch (err) {
      setErrorAccion(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  if (estado.tipo === 'apagado') return null

  return (
    <section aria-label="Seña" className="grid gap-2 border-t pt-3">
      <div className="flex items-center justify-between gap-4">
        <span className="text-muted-foreground">Seña</span>
        {estado.tipo === 'cargando' && <span className="text-muted-foreground">Cargando…</span>}
        {estado.tipo === 'sin' && <span className="text-muted-foreground">Sin seña</span>}
        {estado.tipo === 'sena' && (
          <span className="flex items-center gap-2">
            <span className="font-medium">{formatMonto(estado.sena.amount)}</span>
            <BadgeSena estado={estado.sena.status} />
          </span>
        )}
      </div>
      {estado.tipo === 'sena' && estado.sena.medio_pago && (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">Cobrada con</span>
          <span className="font-medium">{nombreMedio(medios, estado.sena.medio_pago)}</span>
        </div>
      )}
      {estado.tipo === 'error' && <p className="text-sm text-destructive">{estado.mensaje}</p>}

      {estado.tipo === 'sin' && ADMITE_SENA.has(turno.status) && (
        <Form {...form}>
          <form className="flex items-end gap-2" onSubmit={form.handleSubmit(pedir)}>
            <FormField
              control={form.control}
              name="amount"
              render={({ field }) => (
                <FormItem className="flex-1">
                  <FormLabel>Monto de la seña</FormLabel>
                  <FormControl>
                    <Input inputMode="decimal" placeholder="0,00" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" variant="outline" disabled={form.formState.isSubmitting}>
              Pedir seña
            </Button>
          </form>
        </Form>
      )}

      {estado.tipo === 'sena' && esAdmin && (
        <div className="flex flex-wrap justify-end gap-2">
          {estado.sena.status === 'pending' && (
            <>
              <Button size="sm" variant="outline" onClick={() => setConfirmando('fallida')}>
                Marcar fallida
              </Button>
              <Button size="sm" onClick={() => setCobrando(estado.sena)}>Cobrar seña</Button>
            </>
          )}
          {estado.sena.status === 'paid' && (
            <Button size="sm" variant="outline" onClick={() => setConfirmando('devolver')}>
              Devolver seña
            </Button>
          )}
        </div>
      )}
      {estado.tipo === 'sena' && !esAdmin && estado.sena.status === 'pending' && (
        <p className="text-xs text-muted-foreground">
          El cobro de la seña lo registra un administrador.
        </p>
      )}
      {errorAccion && <p className="text-sm text-destructive">{errorAccion}</p>}

      <CobrarSenaDialog
        sena={cobrando}
        medios={medios}
        onClose={() => setCobrando(null)}
        onCobrada={async () => { setCobrando(null); await cargar() }}
      />
      {estado.tipo === 'sena' && (
        <ConfirmDialog
          open={confirmando !== null}
          onOpenChange={(abierto) => { if (!abierto) setConfirmando(null) }}
          title={confirmando === 'devolver' ? '¿Devolver la seña?' : '¿Marcar la seña como fallida?'}
          description={confirmando === 'devolver'
            ? `Se registra la devolución de ${formatMonto(estado.sena.amount)}. No se puede deshacer.`
            : 'La seña queda como no cobrada y ya no se puede cobrar. No se puede deshacer.'}
          confirmLabel={confirmando === 'devolver' ? 'Devolver' : 'Marcar fallida'}
          onConfirm={() => transicion(estado.sena, confirmando === 'devolver' ? 'refund' : 'mark-failed')}
        />
      )}
    </section>
  )
}

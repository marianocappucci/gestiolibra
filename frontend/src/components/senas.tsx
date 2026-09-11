/** Los componentes de seña que comparten la pantalla de Señas y el detalle del
 *  turno. Las constantes y el formato de monto están en `lib/senas.ts`.
 */
import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { api, ApiError, SENA_LABELS, type EstadoSena, type MedioPago } from '../api'
import { SENA_TONO, formatMonto } from '@/lib/senas'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

export function BadgeSena({ estado }: { estado: EstadoSena }) {
  return <BadgeEstado tono={SENA_TONO[estado]}>{SENA_LABELS[estado]}</BadgeEstado>
}

const cobroSchema = z.object({
  medio_pago: z.string().min(1, 'Elegí cómo se cobró'),
})

type CobroValues = z.infer<typeof cobroSchema>

/** El cobro de una seña: `POST /deposits/{id}/mark-paid` con su medio de pago.
 *
 *  🔴 **El medio de pago es obligatorio acá aunque el backend lo acepte vacío.**
 *  Cuando el turno se completa y se factura, `invoice_appointment`
 *  (`app/services/billing.py`) registra la seña como un movimiento de caja con
 *  `medio_pago=deposit.medio_pago or ""`: una seña cobrada sin medio entra a la
 *  caja con el medio en blanco, sin decir si fue efectivo o transferencia. */
export function CobrarSenaDialog({
  sena, medios, onClose, onCobrada,
}: {
  sena: { id: string; amount: string } | null
  medios: MedioPago[]
  onClose: () => void
  onCobrada: () => void | Promise<void>
}) {
  const [error, setError] = useState<string | null>(null)
  const form = useForm<CobroValues>({
    resolver: zodResolver(cobroSchema),
    defaultValues: { medio_pago: '' },
  })

  useEffect(() => {
    if (sena) {
      form.reset({ medio_pago: '' })
      setError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sena?.id])

  async function cobrar(values: CobroValues) {
    if (!sena) return
    setError(null)
    try {
      await api.post(`/deposits/${sena.id}/mark-paid`, { medio_pago: values.medio_pago })
      await onCobrada()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  return (
    <Dialog open={sena !== null} onOpenChange={(abierto) => { if (!abierto) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cobrar seña</DialogTitle>
          <DialogDescription>
            {sena ? `Seña de ${formatMonto(sena.amount)}. ` : ''}
            Elegí cómo se cobró: al completar el turno se descuenta del total y
            entra a la caja con este medio.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form className="grid gap-3" onSubmit={form.handleSubmit(cobrar)}>
            <FormField
              control={form.control}
              name="medio_pago"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Medio de pago</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger><SelectValue placeholder="Medio de pago…" /></SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {medios.map((m) => (
                        <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? 'Cobrando…' : 'Registrar cobro'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

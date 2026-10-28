/** La factura de un turno completado y su nota de crédito, dentro de su detalle en la agenda (ADR-039).
 *
 *  Es el único lugar donde este producto muestra una factura ya emitida (ADR-027: no hay una lista de facturas), así que es
 *  donde vive el botón «Nota de crédito». Muestra la factura, sus notas, el PDF de cada una y lo que falta acreditar.
 *
 *  **Quién hace qué** — lo decide el backend, acá sólo se refleja:
 *  - Ver la factura y bajar el PDF: admin y staff.
 *  - Emitir la nota de crédito: sólo admin (es plata y un documento fiscal que no se deshace). Al staff no se le muestra el
 *    botón; si lo tocara, el backend le contestaría 403.
 *  - En el equipo del local sin conexión (ADR-036) la nota es del central: se ve la factura, pero la nota se emite desde la web.
 *
 *  ⚠️ **Sin el módulo `facturacion` en el plan, la sección no aparece** (el backend contesta 403 y un turno sin factura, 404):
 *  mostrar «no tenés acceso» adentro de cada turno sería ruido sobre una función que el cliente no contrató.
 */
import { useCallback, useEffect, useState } from 'react'
import { FileMinus, FileText } from 'lucide-react'
import { DestinoDeNotaDeCredito } from 'libra-ui/DestinoDeNotaDeCredito'
import {
  SIN_ELEGIR, avisoDeReintegro, cuerpoDeDestino, faltaElegirDestino, useOfertaDeDestino,
  type DestinoElegido,
} from 'libra-ui/destino-de-nota'
import { formatoMoneda } from 'libra-ui/formatos'
import {
  api, ApiError, type ComprobanteDelTurno, type FacturaDelTurno,
} from '../../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import type { TurnoConRecurso } from './datos'
import {
  MOTIVO_MAXIMO, MOTIVO_MINIMO, etiquetaDeComprobante, importeEscrito, tieneCae,
} from '@/lib/factura-del-turno'

/** Lo que se sabe de la factura del turno. `sin` es el 404 (no se facturó) y el 403 del módulo. */
type Estado =
  | { tipo: 'cargando' }
  | { tipo: 'sin' }
  | { tipo: 'error'; mensaje: string }
  | { tipo: 'factura'; detalle: FacturaDelTurno }

function PdfDelComprobante({ c }: { c: ComprobanteDelTurno }) {
  return (
    <Button asChild variant="outline" size="sm">
      <a href={`/api/facturas/${c.id}/pdf`} target="_blank" rel="noreferrer" aria-label={`PDF de ${etiquetaDeComprobante(c)}`}>
        <FileText />PDF
      </a>
    </Button>
  )
}

export function FacturaDelTurno({
  turno, esAdmin, soloLectura = false,
}: {
  turno: TurnoConRecurso
  esAdmin: boolean
  /** En el equipo del local sin conexión la nota de crédito se emite desde la web (409 `solo_en_el_central`). */
  soloLectura?: boolean
}) {
  const [estado, setEstado] = useState<Estado>({ tipo: 'cargando' })
  const [emitiendo, setEmitiendo] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)
  const completado = turno.status === 'completed'

  const cargar = useCallback(async () => {
    try {
      const detalle = await api.get<FacturaDelTurno>(`/appointments/${turno.id}/factura`)
      // Sin `factura` no es la respuesta de este endpoint, sea lo que sea que llegó (el catch-all de la SPA contesta 200).
      setEstado(detalle && typeof detalle === 'object' && detalle.factura ? { tipo: 'factura', detalle } : { tipo: 'sin' })
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 403)) setEstado({ tipo: 'sin' })
      else setEstado({ tipo: 'error', mensaje: err instanceof ApiError ? err.detail : 'Error de conexión.' })
    }
  }, [turno.id])

  // Sin reiniciar el estado acá: quien la monta le pone `key={turno.id}`, así que cada turno arranca de cero.
  useEffect(() => {
    if (completado) void cargar()
  }, [completado, cargar])

  if (!completado || estado.tipo === 'sin') return null
  if (estado.tipo === 'cargando') {
    return <p className="border-t pt-3 text-sm text-muted-foreground">Cargando la factura…</p>
  }
  if (estado.tipo === 'error') {
    return <p role="alert" className="border-t pt-3 text-sm text-destructive">{estado.mensaje}</p>
  }

  const { detalle } = estado
  const { factura, notas_credito: notas } = detalle

  return (
    <section aria-label="Factura del turno" className="grid gap-2 border-t pt-3 text-sm" data-testid="factura-del-turno">
      <div className="flex items-center justify-between gap-3">
        <span>
          <span className="block font-medium">{etiquetaDeComprobante(factura)}</span>
          <span className="text-muted-foreground">
            {formatoMoneda(factura.total)} · {tieneCae(factura) ? `CAE ${factura.cae}` : 'Sin CAE'}
          </span>
        </span>
        <PdfDelComprobante c={factura} />
      </div>

      {notas.map((n) => (
        <div key={n.id} className="flex items-center justify-between gap-3" data-testid="nota-de-credito">
          <span>
            <span className="block font-medium">{etiquetaDeComprobante(n)}</span>
            <span className="text-muted-foreground">
              − {formatoMoneda(n.total)} · {tieneCae(n) ? `CAE ${n.cae}` : 'Sin CAE: ARCA todavía no la autorizó'}
            </span>
          </span>
          <PdfDelComprobante c={n} />
        </div>
      ))}
      {notas.length > 0 && (
        <p className="text-muted-foreground" data-testid="acreditado">
          Acreditado {formatoMoneda(detalle.acreditado)} de {formatoMoneda(factura.total)}
          {detalle.saldo_acreditable > 0 && <> · quedan {formatoMoneda(detalle.saldo_acreditable)}</>}
        </p>
      )}
      {aviso && <p role="status" className="text-muted-foreground">{aviso}</p>}

      {esAdmin && !soloLectura && detalle.puede_acreditar && (
        <div>
          <Button variant="outline" size="sm" disabled={emitiendo} onClick={() => setEmitiendo(true)}>
            <FileMinus />Nota de crédito
          </Button>
        </div>
      )}
      {esAdmin && soloLectura && detalle.puede_acreditar && (
        <p className="text-muted-foreground">La nota de crédito se emite desde la web: el equipo del local no tiene el certificado de ARCA.</p>
      )}

      {/* Se monta al abrirlo y se desmonta al cerrarlo: cada nota arranca limpia, sin el motivo ni el destino de la anterior. */}
      {emitiendo && (
        <NotaDeCreditoDialog
          turnoId={turno.id}
          detalle={detalle}
          onClose={() => setEmitiendo(false)}
          onEmitida={async (respuesta) => {
            setEmitiendo(false)
            setAviso(avisoDeReintegro(respuesta))
            await cargar()
          }}
        />
      )}
    </section>
  )
}

/** El diálogo que emite la nota: confirma sobre qué factura y por cuánto, pide el motivo y, si la factura ya está cobrada,
 *  qué pasa con la plata (`DestinoDeNotaDeCredito` del kit, que pregunta al motor). Está abierto mientras esté montado. */
export function NotaDeCreditoDialog({
  turnoId, detalle, onClose, onEmitida,
}: {
  turnoId: string
  detalle: FacturaDelTurno
  onClose: () => void
  onEmitida: (respuesta: unknown) => void | Promise<void>
}) {
  const [parcial, setParcial] = useState(false)
  const [importeTexto, setImporteTexto] = useState('')
  const [motivo, setMotivo] = useState('')
  const [destino, setDestino] = useState<DestinoElegido>(SIN_ELEGIR)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Una factura que ya tiene notas no admite una total: la nota es siempre por un importe (el motor da 409 `ya_tiene_nota`).
  const yaTieneNotas = detalle.notas_credito.length > 0
  const esParcial = parcial || yaTieneNotas
  const saldo = detalle.saldo_acreditable
  const importe = importeEscrito(importeTexto)
  const importeValido = importe !== null && importe <= saldo + 0.005
  const importeDeLaNota = esParcial ? (importeValido ? importe : null) : null

  // La pregunta de la plata es por el importe de esta nota. Con un importe todavía inválido no se pregunta nada: no se puede emitir.
  const preguntar = !esParcial || importeValido
  const { oferta, cargando } = useOfertaDeDestino(
    preguntar ? `/appointments/${turnoId}/nota-credito/destino` : null, importeDeLaNota)

  const motivoLimpio = motivo.trim().replace(/\s+/g, ' ')
  const motivoValido = motivoLimpio.length >= MOTIVO_MINIMO && motivoLimpio.length <= MOTIVO_MAXIMO
  const puedeEmitir = !enviando && motivoValido && (!esParcial || importeValido) && !cargando
    && !faltaElegirDestino(oferta, destino)

  async function emitir() {
    if (!puedeEmitir) return
    setEnviando(true)
    setError(null)
    try {
      const respuesta = await api.post<unknown>(`/appointments/${turnoId}/nota-credito`, {
        motivo: motivoLimpio,
        ...(esParcial && importe !== null ? { importe: importe.toFixed(2) } : {}),
        ...cuerpoDeDestino(oferta, destino),
      })
      await onEmitida(respuesta)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      setEnviando(false)
    }
  }

  return (
    <Dialog open onOpenChange={(abierto) => { if (!abierto && !enviando) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Emitir nota de crédito</DialogTitle>
          <DialogDescription>
            Anula ante ARCA {esParcial ? 'parte de ' : ''}la {etiquetaDeComprobante(detalle.factura)}
            {' '}({formatoMoneda(detalle.factura.total)}). La nota sale con su CAE y <strong>no se puede deshacer</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 text-sm">
          <fieldset className="grid gap-2">
            <legend className="mb-1 font-medium">Importe</legend>
            <label className="flex items-center gap-2">
              <input type="radio" name="alcance-nota" checked={!esParcial} disabled={yaTieneNotas}
                     onChange={() => setParcial(false)} />
              Total: {formatoMoneda(detalle.saldo_acreditable)}
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" name="alcance-nota" checked={esParcial} onChange={() => setParcial(true)} />
              Parcial
            </label>
            {esParcial && (
              <div className="grid gap-1 pl-6">
                <Label htmlFor="importe-nota">Importe a acreditar (con IVA)</Label>
                <Input
                  id="importe-nota" inputMode="decimal" className="w-40" value={importeTexto}
                  onChange={(e) => setImporteTexto(e.target.value)} placeholder="0,00"
                  aria-invalid={importeTexto !== '' && !importeValido}
                />
                <p className={importeTexto !== '' && !importeValido ? 'text-destructive' : 'text-muted-foreground'}>
                  {importeTexto !== '' && !importeValido
                    ? `Poné un monto de hasta ${formatoMoneda(saldo)}, con dos decimales como máximo.`
                    : `Se puede acreditar hasta ${formatoMoneda(saldo)}.`}
                </p>
              </div>
            )}
          </fieldset>

          {oferta && <DestinoDeNotaDeCredito oferta={oferta} elegido={destino} onChange={setDestino} />}

          <div className="grid gap-1">
            <Label htmlFor="motivo-nota">Motivo</Label>
            <Input
              id="motivo-nota" value={motivo} maxLength={MOTIVO_MAXIMO} autoComplete="off"
              onChange={(e) => setMotivo(e.target.value)} placeholder="Ej.: se facturó el servicio equivocado"
            />
            <p className="text-muted-foreground">Queda en el registro de actividad, con quién la emitió. Al menos {MOTIVO_MINIMO} letras.</p>
          </div>

          {error && <p role="alert" className="text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={enviando} onClick={onClose}>Cancelar</Button>
          <Button disabled={!puedeEmitir} onClick={() => void emitir()}>
            {enviando ? 'Emitiendo…' : 'Emitir nota de crédito'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Cómo se rotula en la pantalla cada `tipo` de aviso del registro (ADR-040). El `tipo` lo pone quien avisa, así que el vocabulario es de
// este producto: hoy sólo hay uno, el recordatorio de turno (`libracore.avisos.agenda.TIPO`).

/** Lo que no esté acá se muestra tal cual lo mandó el motor. */
export const TIPOS_DE_AVISO: Record<string, string> = {
  recordatorio: 'Recordatorio de turno',
}

export const etiquetaDelTipo = (tipo: string) => TIPOS_DE_AVISO[tipo] ?? tipo

/** Las condiciones frente al IVA que ofrece el formulario de cliente: un catálogo cerrado de ARCA, fijo en el código. */
export const CONDICIONES_IVA = [
  'Responsable Inscripto',
  'Monotributista',
  'IVA Exento',
  'Consumidor Final',
  'No Alcanzado',
]

/** De la condición que informa el padrón de ARCA a la de este formulario: las mismas palabras, salvo las que aquí no
 *  existen («IVA No Responsable»), que devuelven `undefined` y dejan la condición como estaba. */
export const condicionDeArca = (condicion: string): string | undefined =>
  CONDICIONES_IVA.includes(condicion) ? condicion : undefined

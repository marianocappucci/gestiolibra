# Decisiones arquitectónicas — Gestiolibra

Registro ADR. Las decisiones no se borran; si dejan de aplicar, se marcan como reemplazadas.

## ADR-001 — Usar LibraGenda como motor de agenda

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: Gestiolibra necesita turnos, disponibilidad, recursos y servicios sin incorporar lógica clínica.
- Decisión: consumir LibraGenda como dependencia versionada y mantener en Gestiolibra solo el flujo HTTP y las reglas del vertical.
- Consecuencias: reutilización entre verticales y menor duplicación; los cambios genéricos deben corregirse upstream.

## ADR-002 — Corregir problemas del motor en LibraGenda, no con workarounds locales

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: se detectaron diferencias reales entre SQLite y PostgreSQL y faltantes CRUD en el repositorio compartido.
- Decisión: corregir el comportamiento común en LibraGenda, versionarlo con tag y actualizar el pin del consumidor.
- Consecuencias: un único contrato para consumidores, con promoción y verificación separadas.

## ADR-003 — Ejecutar migraciones de LibraGenda desde el repo upstream

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: las migraciones no forman parte del wheel de LibraGenda.
- Decisión: el deploy clona LibraGenda en el tag pineado y ejecuta Alembic antes de levantar Gestiolibra.
- Consecuencias: las migraciones tienen una sola fuente de verdad y el deploy es reproducible.

## ADR-004 — Mantener el producto fuera de dominios no clínicos

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: la familia Libra tiene verticales de salud y gastronomía independientes.
- Decisión: excluir de Gestiolibra historia clínica, recetas, estudios y funcionalidades gastronómicas.
- Consecuencias: el producto conserva un alcance claro para negocios de servicios generales.

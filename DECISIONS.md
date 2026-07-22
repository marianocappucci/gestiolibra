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

## ADR-005 — Reusar SessionAuth de LibraCore, tabla de usuarios propia

- Estado: aceptada
- Fecha: 2026-07-21
- Contexto: Gestiolibra necesita login y roles (`admin`/`staff`). LibraCore
  ya tiene `SessionAuth` (cookie firmada, roles, probado en producción por
  Contalibra/Restolibra), diseñado explícitamente para reusarse entre
  productos (recibe callbacks en vez de asumir un schema). Su tabla de
  usuarios (`libracore.db.usuarios`) no sirve tal cual: está acoplada a
  SQLite vía `libracore.db.core.get_connection` con SQL crudo, y Gestiolibra
  usa PostgreSQL/SQLAlchemy.
- Decisión: sumar `libracore` como dependencia solo por `SessionAuth` (la
  mecánica de cookie/sesión, agnóstica de storage). Tabla `users` propia en
  SQLAlchemy/PostgreSQL con el mismo algoritmo de hashing (PBKDF2, 260k
  iteraciones) que `libracore.db.usuarios`, reimplementado en
  `app/security.py` en vez de importar las funciones privadas
  (prefijo `_`) de ese módulo.
- Consecuencias: Gestiolibra no reinventa la mecánica de sesión/cookie (ya
  auditada), pero sí duplica ~20 líneas de hashing puro sin dependencias —
  trade-off aceptado sobre acoplarse a un módulo interno de otro paquete no
  pensado para reuso directo. `SessionAuth.require_auth`/`require_role`
  (con redirect 307 a `/login`) tampoco se reusan: Gestiolibra es una API
  JSON pura sin esa página, así que `app/auth.py` define sus propias
  dependencias con 401/403.

## ADR-006 — Dos roles para el MVP: admin y staff

- Estado: aceptada
- Fecha: 2026-07-21
- Contexto: el negocio necesita diferenciar quién administra el negocio
  (sucursales, recursos, servicios, clientes, usuarios) de quién solo
  atiende turnos (empleados).
- Decisión: `admin` con acceso completo; `staff` limitado a `/appointments`
  y `/resources/{id}/agenda` — no puede tocar catálogo ni gestionar otros
  usuarios. Gating aplicado centralizado por router en `app/main.py`, no
  repetido endpoint por endpoint.
- Consecuencias: esquema simple y suficiente para el MVP; agregar roles más
  finos (ej. gerente de sucursal) queda para cuando aparezca una necesidad
  real, no se anticipa.

## ADR-007 — Alembic propio de Gestiolibra, cadena independiente de la de LibraGenda

- Estado: aceptada
- Fecha: 2026-07-21
- Contexto: la tabla `users` (y cualquier tabla futura que no pertenezca a
  LibraGenda) solo se creaba vía `Base.metadata.create_all()` en
  `create_app()` — sin efecto real en un deploy de producción, que no llama
  a `create_all()` sino que corre las migraciones de LibraGenda (ver
  ADR-003). Sin una migración propia, `users` nunca se hubiera creado fuera
  de dev/tests.
- Decisión: `migrations/` propio en este repo (mismo layout que LibraGenda:
  `alembic.ini`, `env.py`, `versions/`), pero con dos diferencias
  deliberadas: (1) `target_metadata = None` en vez de `Base.metadata` —
  `UserRow` comparte el `Base` declarativo de LibraGenda, así que apuntar
  el autogenerate ahí vería también las tablas del motor como propias de
  esta cadena; las migraciones se escriben a mano, igual que ya hace
  LibraGenda. (2) `version_table = "alembic_version_gestiolibra"` — ambas
  cadenas corren contra la misma base física; con el nombre default
  colisionarían.
- Consecuencias: el deploy real de Gestiolibra corre dos pasos de Alembic
  en vez de uno (LibraGenda primero, Gestiolibra después) — verificado
  contra PostgreSQL real que las dos cadenas de versión conviven sin
  pisarse. Cualquier tabla nueva propia de Gestiolibra (no de LibraGenda)
  se agrega acá, nunca en el repo de LibraGenda.

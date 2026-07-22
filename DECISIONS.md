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

## ADR-008 — Configuración comercial: opt-in, y separada de LibraGenda

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: "configuración comercial" estaba anotada en `TASKS.md` desde
  el scaffold sin nunca detallarse. Preguntado al usuario, se acordó
  alcance concreto: horario comercial por sucursal, precio por servicio y
  sucursal, y datos de contacto/marca del negocio.
- Decisión: las tres piezas quedan como tablas propias de Gestiolibra
  (`branch_hours`, `service_prices`, `branch_contacts`,
  `business_settings`), no en LibraGenda — el motor no calcula precios
  (mismo principio que señas/`Deposit`) ni tiene noción de "horario del
  negocio" a nivel sucursal (solo disponibilidad por recurso), y ningún
  otro vertical de la familia pidió esto todavía como para justificar
  subirlo al motor compartido (ver ADR-002: los cambios genéricos se
  corrigen en LibraGenda, pero esto no es un cambio genérico probado por
  dos consumidores, es específico de este negocio por ahora). El horario
  comercial es **opt-in**: una sucursal sin horario configurado no gatea
  nada — se decidió así para no romper ningún flujo de turnos existente
  con una restricción nueva no pedida; solo al configurarlo se exige
  además de la disponibilidad del recurso (intersección).
- Consecuencias: si MedLibra (o un futuro vertical) pide horario comercial
  por sucursal, evaluar en ese momento si conviene subirlo a LibraGenda
  (misma señal que ya disparó la extracción de CRUD de catálogo y el fix
  de datetimes). Precio y contacto/marca son negocio/vertical-specific casi
  con certeza — poco probable que se generalicen.

## ADR-009 — Recordatorios y señas: puertos placeholder hasta elegir proveedor

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: LibraGenda ya resuelve el dominio de recordatorios
  (`ReminderDispatcher`, `due_reminders()`) y señas (`DepositManager`) vía
  dos puertos (`NotificationPort`, `PaymentPort`) que Gestiolibra debe
  implementar. No hay todavía un proveedor de notificaciones (email/SMS/
  WhatsApp) ni de pagos (MercadoPago u otro) elegido para el negocio.
  Preguntado al usuario cómo resolver ambos vacíos antes de codificar.
- Decisión: implementar ambos puertos como placeholders explícitos en vez
  de bloquear la feature o improvisar una integración real a medias.
  `LoggingNotificationPort` loguea cada recordatorio vencido en vez de
  enviarlo. `ManualPaymentPort` no cobra ni reintegra solo — `request_charge`/
  `request_refund` solo loguean la intención; la confirmación real de la
  seña (efectivo, transferencia, link de MercadoPago enviado a mano) la
  hace un admin a mano vía `POST /deposits/{id}/mark-paid`/`mark-failed`/
  `refund`. Los dos endpoints de disparo (`/reminders/dispatch`) y consulta/
  confirmación de señas quedan operativos igual, con el reemplazo del canal
  como el único trabajo pendiente cuando se elija proveedor.
- Consecuencias: la feature es usable en producción sin esperar una
  integración externa (recordatorios visibles en logs para seguimiento
  manual, señas cobradas y confirmadas por el propio negocio). El costo es
  operativo, no técnico: alguien tiene que mirar los logs y marcar los pagos
  a mano hasta que se reemplacen los puertos. `NotificationPort`/
  `PaymentPort` son `Protocol` sin `@runtime_checkable`, así que la
  conformidad es estructural (duck typing), no verificada por `isinstance`.

## ADR-010 — SQLite como destino de producción por defecto

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: al scopear si MedLibra debía componer LibraCore para
  facturación, salió a la luz que Contalibra/Restolibra despliegan con
  arquitectura silo real (instancia + base SQLite aislada por cliente) y
  que Gestiolibra ya prevé exactamente el mismo patrón de despliegue
  (Docker, `panel_admin.py`, sin infraestructura de producción propia
  todavía — ver "Infraestructura" en la entidad de este repo en la wiki).
  Mantener Gestiolibra en PostgreSQL mientras el resto de la familia usa
  SQLite no aportaba nada real y complicaba cualquier composición futura
  con LibraCore (SQLite-only, sin capa de abstracción). Decisión del
  usuario, registrada como estándar de familia en LibraGenda (ver
  `DECISIONS.md` de ese repo, ADR-005) y en `estandares-desarrollo.md`
  del wiki.
- Decisión: `DATABASE_URL` pasa a apuntar a un archivo SQLite por
  defecto en vez de una base Postgres. Sin cambios de código propios:
  `LibraGenda.configure(url)` ya activa `PRAGMA foreign_keys=ON`
  automáticamente para cualquier conexión SQLite (ver ADR-005 de
  LibraGenda) — antes esto solo se probaba contra SQLite en memoria
  (tests) o contra Postgres real, nunca contra un archivo SQLite con FKs
  forzadas. Al verificar contra un archivo real con FKs activas, salió
  a la luz un bug preexistente (no introducido por este cambio, ya
  estaba ahí desde que se creó `BranchRepository`): `delete()` borraba
  el `Branch` genérico de LibraGenda **antes** que `BranchContactRow`
  (extensión propia con FK a `branches.id`) — mismo patrón de bug que
  `PatientRepository.delete()` de MedLibra (ver `DECISIONS.md` de ese
  repo, ADR-011). Postgres ya lo hubiera bloqueado siempre (fuerza FKs
  por default); nunca se ejerció ese camino contra Postgres real en las
  verificaciones anteriores. Corregido invirtiendo el orden. De paso se
  encontró que `DELETE /branches/{id}`, `/resources/{id}`,
  `/services/{id}` y `/clients/{id}` no traducían `IntegrityError` a un
  409 limpio (solo capturaban `KeyError`) — cualquier intento de borrar
  una entidad de catálogo con dependientes devolvía un 500 crudo en vez
  de un error entendible. Agregado el `except IntegrityError` faltante
  en los cuatro routers.
- Consecuencias: CI simplificado (sin servicio Postgres, smoke check
  contra un archivo SQLite plano). Verificado con la suite completa y
  end-to-end contra un archivo SQLite real (creación, turno, recordatorio,
  seña, y los tres casos de borrado bloqueado por FK — sucursal con
  recurso, recurso con turno — ahora devolviendo 409 en vez de 500).
  Postgres sigue funcionando si se pasa esa `DATABASE_URL`; no se retira
  como opción.

# Roadmap de Gestiolibra

## Fase 0 — scaffold (completa)

Repo privado, FastAPI, dependencia LibraGenda `v0.3.0`, PostgreSQL dedicado
real (base `gestiolibra`, usuario `gestiolibra_dev`, Postgres 16 del VPS
Donweb) migrado con la cadena Alembic completa de LibraGenda (`0001`→`0006`)
y verificado end-to-end con los repositorios SQLAlchemy reales — no solo el
smoke test sqlite del demo. Cierra el ítem "Gestiolibra usa LibraGenda en un
entorno dev real" de la Fase 3 del roadmap de LibraGenda.

## Fase 1 — MVP operativo (en curso)

- Separar el demo en routers y servicios de aplicación (completo).
  `app/routers/` (health, demo, appointments) + `app/services/` (
  `AppointmentService`, capa de aplicación sobre `InMemoryScheduler`) +
  `app/dependencies.py`. El endpoint `/demo/seed` queda como placeholder
  explícito hasta que lo reemplace el CRUD real del siguiente ítem. Se
  amplió la cobertura de tests HTTP a las ramas de error (servicio
  inexistente, conflicto de horario, fuera de disponibilidad, turno
  inexistente, doble confirmación) que antes solo se probaban por el
  camino feliz.
- CRUD de sucursales, recursos, servicios y clientes (completo). Routers
  `branches`, `resources`, `services`, `clients` con create/list/get/
  update/delete real, reemplazando el `/demo/seed`. Requirió extender
  `SqlAlchemyCatalogRepository` de LibraGenda (upstream) con `get_x`/
  `update_x`/`delete_x` — solo tenía `add_x`/`list_x`; se corrigió ahí, no
  con un shim local, siguiendo la regla de no duplicar reglas/persistencia
  de LibraGenda (LibraGenda `v0.4.1`, tag patch). Verificado contra la base
  real de Gestiolibra en el VPS, no solo sqlite.
- Agenda diaria/semanal y disponibilidad configurable por negocio
  (completo). `/resources/{id}/availability` (ventanas semanales),
  `/blocks` (bloqueos puntuales), `/exceptions` (excepciones por fecha) —
  CRUD completo sobre `SqlAlchemyAvailabilityRepository` de LibraGenda.
  `/resources/{id}/agenda?date_from=&date_to=` devuelve los turnos del
  recurso en el rango. **Cambio de comportamiento real**: `AppointmentService.create()`
  dejó de usar una ventana 9-18 hardcodeada — ahora lee la disponibilidad
  real configurada (ventanas + bloqueos + excepciones); un recurso sin
  disponibilidad configurada ya no puede recibir turnos (409). Encontró un
  bug real de LibraGenda en el camino: `DateTime(timezone=True)` vuelve
  *naive* en SQLite (sin tipo timestamptz nativo) pero *aware* en
  PostgreSQL — mismo dato, comportamiento distinto por dialecto, invisible
  en dev con sqlite pero rompía comparaciones de intervalos contra la base
  real. Corregido upstream en LibraGenda (`ensure_utc()` en las
  conversiones fila→dominio, tag `v0.4.2`) — otra vez el mismo patrón:
  arreglar en el motor, no con un workaround local.
- Cancelar y reprogramar con motivos.
- Login y roles básicos.

## Fase 2 — operación comercial

- Recordatorios.
- Señas y políticas de cancelación.
- Caja/facturación componiendo LibraCore.
- Dashboard y reportes.

## Fase 3 — producto

- Onboarding multi-negocio.
- Branding y dominio por cliente.
- Deploy dev/prod, CI y backups verificados.
- Validación con primeros negocios reales.

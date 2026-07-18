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
- CRUD de sucursales, recursos, servicios y clientes.
- Agenda diaria/semanal y disponibilidad configurable por negocio.
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

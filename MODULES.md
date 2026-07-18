# Módulos de Gestiolibra

## Implementados

- `app/main.py`: factory FastAPI — configura LibraGenda, arma repos/servicios
  en `app.state`, monta routers.
- `app/dependencies.py`: providers de FastAPI que leen `app.state`.
- `app/services/appointments.py`: `AppointmentService` — capa de aplicación
  que delega en `InMemoryScheduler` de LibraGenda. Reglas propias: el
  servicio reservado debe existir, y los datetimes de entrada se
  normalizan a UTC-aware en el borde (`_as_utc`) antes de tocar el motor.
  `create()` lee la disponibilidad real del recurso (ventanas + bloqueos +
  excepciones) en vez de una ventana hardcodeada; `agenda()` filtra los
  turnos del recurso por rango de fechas.
- `app/routers/`: `health.py`, `branches.py`, `resources.py`, `services.py`,
  `clients.py` (CRUD completo — create/list/get/update/delete — sobre
  `SqlAlchemyCatalogRepository` de LibraGenda), `availability.py` (CRUD de
  ventanas/bloqueos/excepciones por recurso sobre
  `SqlAlchemyAvailabilityRepository`), `appointments.py`, `agenda.py` —
  traducen excepciones de dominio y `IntegrityError`/`KeyError` a códigos
  HTTP (404/409/422). Reemplazó al `/demo/seed` placeholder.

## MVP (pendiente)

- `business`: configuración comercial más allá del CRUD básico de sucursales.
- Cancelar y reprogramar con motivos.
- Login y roles básicos.
- `billing` (opcional): composición de LibraCore para facturación/caja.

## Después del MVP

- Recordatorios y preferencias de comunicación.
- Señas y políticas de cancelación.
- Dashboard y reportes operativos.

## Fuera de alcance

Historia clínica, recetas, estudios, mesas, comandas, cocina y food cost.

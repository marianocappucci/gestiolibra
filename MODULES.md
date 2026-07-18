# Módulos de Gestiolibra

## Implementados

- `app/main.py`: factory FastAPI — configura LibraGenda, arma repos/servicios
  en `app.state`, monta routers.
- `app/dependencies.py`: providers de FastAPI que leen `app.state`.
- `app/services/appointments.py`: `AppointmentService` — capa de aplicación
  que delega en `InMemoryScheduler` de LibraGenda; la única regla propia es
  validar que el servicio reservado exista.
- `app/routers/`: `health.py`, `branches.py`, `resources.py`, `services.py`,
  `clients.py` (CRUD completo — create/list/get/update/delete — sobre
  `SqlAlchemyCatalogRepository` de LibraGenda), `appointments.py` —
  traducen excepciones de dominio y `IntegrityError`/`KeyError` a códigos
  HTTP (404/409/422). Reemplazó al `/demo/seed` placeholder.

## MVP (pendiente)

- `business`: configuración comercial más allá del CRUD básico de sucursales.
- Agenda diaria/semanal y disponibilidad configurable por negocio.
- Cancelar y reprogramar con motivos.
- Login y roles básicos.
- `billing` (opcional): composición de LibraCore para facturación/caja.

## Después del MVP

- Recordatorios y preferencias de comunicación.
- Señas y políticas de cancelación.
- Dashboard y reportes operativos.

## Fuera de alcance

Historia clínica, recetas, estudios, mesas, comandas, cocina y food cost.

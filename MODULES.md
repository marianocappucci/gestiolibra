# Módulos de Gestiolibra

## Implementados

- `app/main.py`: factory FastAPI — configura LibraGenda, arma repos/servicios
  en `app.state`, monta routers.
- `app/dependencies.py`: providers de FastAPI que leen `app.state`.
- `app/services/appointments.py`: `AppointmentService` — capa de aplicación
  que delega en `InMemoryScheduler` de LibraGenda; la única regla propia es
  validar que el servicio reservado exista.
- `app/routers/`: `health.py`, `demo.py` (placeholder hasta el CRUD real),
  `appointments.py` — traducen excepciones de dominio a códigos HTTP.

## MVP (pendiente)

- `agenda`: composición de LibraGenda para recursos, servicios y turnos.
- `customers`: clientes operativos del negocio.
- `business`: sucursales, configuración comercial y servicios ofrecidos.
- `billing` (opcional): composición de LibraCore para facturación/caja.

## Después del MVP

- Recordatorios y preferencias de comunicación.
- Señas y políticas de cancelación.
- Dashboard y reportes operativos.

## Fuera de alcance

Historia clínica, recetas, estudios, mesas, comandas, cocina y food cost.

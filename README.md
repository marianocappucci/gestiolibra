# Gestiolibra

Vertical de gestión de turnos para negocios de servicios no clínicos:
barberías, peluquerías, estética, lavaderos, talleres y similares.

Compone:

- LibraGenda `v0.3.0` — agenda, recursos, servicios, ciclo de vida de turnos,
  disponibilidad/bloqueos/excepciones, feriados y timezone por sucursal,
  recurrencias, recordatorios (puerto de notificaciones) y señas (puerto de
  pagos).
- LibraCore — administración/facturación/caja, cuando corresponda.

Gestiolibra posee la API HTTP y el flujo de producto. LibraGenda permanece
como paquete reutilizable con PostgreSQL dedicado y migraciones propias —
base `gestiolibra` en el mismo Postgres 16 del VPS Donweb que aloja la de
LibraGenda, migrada con las migraciones del propio paquete de LibraGenda
(no se distribuyen en el wheel de PyPI, se aplican desde un checkout de esa
versión exacta contra `DATABASE_URL`).

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```

La base PostgreSQL y las migraciones de LibraGenda deben estar configuradas
antes de iniciar la aplicación real.

# Gestiolibra

Vertical de gestión de turnos para negocios de servicios no clínicos:
barberías, peluquerías, estética, lavaderos, talleres y similares.

Compone:

- LibraGenda `v0.4.2` — agenda, recursos, servicios, ciclo de vida de turnos,
  disponibilidad/bloqueos/excepciones, feriados y timezone por sucursal,
  recurrencias, recordatorios (puerto de notificaciones) y señas (puerto de
  pagos).
- LibraCore — administración/facturación/caja, cuando corresponda.

API: CRUD real de `/branches`, `/resources`, `/services`, `/clients`;
disponibilidad configurable por recurso (`/resources/{id}/availability`,
`/blocks`, `/exceptions`); `/appointments` (crear/confirmar — ahora valida
contra la disponibilidad real configurada, no una ventana fija); y
`/resources/{id}/agenda` (turnos en un rango de fechas). El endpoint
`/demo/seed` fue reemplazado por el CRUD.

Gestiolibra posee la API HTTP y el flujo de producto. LibraGenda permanece
como paquete reutilizable con PostgreSQL dedicado y migraciones propias —
base `gestiolibra` en el mismo Postgres 16 del VPS Donweb que aloja la de
LibraGenda, migrada con las migraciones del propio paquete de LibraGenda
(no se distribuyen en el wheel de pip; ver más abajo).

## Migraciones de LibraGenda

Las migraciones de Alembic de LibraGenda no viajan en el wheel instalado
por pip (decisión documentada en el `CONVENTIONS.md` de LibraGenda). El
paso de deploy de Gestiolibra debe correr, antes de levantar la API, el
script `scripts/run_migrations.sh` del repo de LibraGenda en el mismo tag
pineado en `pyproject.toml` (hoy `v0.4.2`):

```bash
LIBRAGENDA_REF=v0.4.2 DATABASE_URL="$LIBRAGENDA_DATABASE_URL" \
  bash path/a/libragenda/scripts/run_migrations.sh
```

El script clona LibraGenda en ese tag a un directorio temporal y corre
`alembic upgrade head` contra `DATABASE_URL` sin tocar `alembic.ini`. Es el
mismo paso, reproducible, que reemplaza el sync manual por rsync usado en
dev.

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

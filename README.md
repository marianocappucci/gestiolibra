# Gestiolibra

Vertical de gestión de turnos para negocios de servicios no clínicos:
barberías, peluquerías, estética, lavaderos, talleres y similares.

Compone:

- LibraGenda `v0.5.0` — agenda, recursos, servicios, ciclo de vida de turnos,
  disponibilidad/bloqueos/excepciones, feriados y timezone por sucursal,
  recurrencias, recordatorios (puerto de notificaciones), señas (puerto de
  pagos) y motivo opcional de cancelación/reprogramación.
- LibraCore — solo `libracore.auth.SessionAuth` por ahora (login por cookie
  firmada); administración/facturación/caja, cuando corresponda.

API: `/auth/login`, `/auth/logout`, `/auth/me` (sesión por cookie); CRUD de
usuarios en `/users` (solo `admin`); CRUD real de `/branches`, `/resources`,
`/services`, `/clients` (solo `admin`); disponibilidad configurable por
recurso (`/resources/{id}/availability`, `/blocks`, `/exceptions`, solo
`admin`); `/appointments` (crear/confirmar/cancelar/reprogramar — `admin` o
`staff`, valida contra la disponibilidad real configurada, no una ventana
fija; cancelar y reprogramar aceptan un `reason` opcional en el body); y
`/resources/{id}/agenda` (turnos en un rango de fechas, `admin` o `staff`).
El endpoint `/demo/seed` fue reemplazado por el CRUD.

## Autenticación

Sesión por cookie firmada (`gl_session`), sin API keys ni JWT todavía. Al
arrancar sin usuarios, se crea un admin de bootstrap
(`GESTIOLIBRA_ADMIN_USERNAME`/`GESTIOLIBRA_ADMIN_PASSWORD`; sin contraseña
configurada la app no levanta salvo `ENV=development`, donde usa
`admin`/`admin`). Roles: `admin` (todo) y `staff` (solo `/appointments` y
`/resources/{id}/agenda`).

Gestiolibra posee la API HTTP y el flujo de producto. LibraGenda permanece
como paquete reutilizable con PostgreSQL dedicado y migraciones propias —
base `gestiolibra` en el mismo Postgres 16 del VPS Donweb que aloja la de
LibraGenda, migrada con las migraciones del propio paquete de LibraGenda
(no se distribuyen en el wheel de pip; ver más abajo).

## Migraciones

Dos cadenas de Alembic independientes corren contra la **misma** base
`gestiolibra`, cada una con su propia tabla de versión (para no
pisarse: `alembic_version` es de LibraGenda, `alembic_version_gestiolibra`
es de Gestiolibra). El deploy corre ambas, en este orden, antes de levantar
la API:

**1. Migraciones de LibraGenda** (schema del motor: sucursales, recursos,
servicios, clientes, turnos, disponibilidad...). No viajan en el wheel
instalado por pip (decisión documentada en el `CONVENTIONS.md` de
LibraGenda), así que se aplican clonando el repo en el tag pineado en
`pyproject.toml` (hoy `v0.5.0`):

```bash
LIBRAGENDA_REF=v0.5.0 DATABASE_URL="$DATABASE_URL" \
  bash path/a/libragenda/scripts/run_migrations.sh
```

**2. Migraciones propias de Gestiolibra** (tabla `users` — no pertenece al
dominio de LibraGenda, ver `MODULES.md`). Viajan en este mismo repo, se
aplican directamente:

```bash
DATABASE_URL="$DATABASE_URL" alembic upgrade head
```

`migrations/env.py` deja `target_metadata = None` a propósito: `UserRow`
está registrado en el `Base` compartido de LibraGenda (mismo objeto
SQLAlchemy), así que apuntar el autogenerate ahí vería también las tablas
de LibraGenda como propias de esta cadena. Las migraciones de Gestiolibra
se escriben a mano, mismo criterio que ya usa LibraGenda para las suyas.

## Documentación

- [ROADMAP.md](ROADMAP.md) — dirección estratégica.
- [TASKS.md](TASKS.md) — trabajo concreto vigente.
- [ARCHITECTURE.md](ARCHITECTURE.md) — arquitectura actual.
- [CONVENTIONS.md](CONVENTIONS.md) — estándares del código.
- [DECISIONS.md](DECISIONS.md) — decisiones y motivos.
- [CHANGELOG.md](CHANGELOG.md) — cambios publicados.
- [MODULES.md](MODULES.md) — inventario de módulos.

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

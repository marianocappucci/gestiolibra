# Gestiolibra

Vertical de gestión de turnos para negocios de servicios no clínicos:
barberías, peluquerías, estética, lavaderos, talleres y similares.

Compone:

- LibraGenda `v0.6.0` — agenda, recursos, servicios, ciclo de vida de turnos,
  disponibilidad/bloqueos/excepciones, feriados y timezone por sucursal,
  recurrencias, recordatorios (puerto de notificaciones), señas (puerto de
  pagos) y motivo opcional de cancelación/reprogramación.
- LibraCore — solo `libracore.auth.SessionAuth` por ahora (login por cookie
  firmada); administración/facturación/caja, cuando corresponda.

API: `/auth/login`, `/auth/logout`, `/auth/me` (sesión por cookie); CRUD de
usuarios en `/users` (solo `admin`); CRUD real de `/branches` (incluye
`phone`/`address`), `/resources`, `/services`, `/clients` (solo `admin`);
horario comercial por sucursal en `/branches/{id}/hours` (opt-in — sin
configurar no gatea nada); precio por servicio y sucursal en
`/services/{id}/prices`; datos globales del negocio (nombre comercial,
moneda) en `/business`; disponibilidad configurable por recurso
(`/resources/{id}/availability`, `/blocks`, `/exceptions`, solo `admin`);
`/appointments` (crear/confirmar/cancelar/reprogramar — `admin` o `staff`,
valida contra la disponibilidad real configurada y el horario comercial de
la sucursal si está configurado; cancelar y reprogramar aceptan un
`reason` opcional en el body); `/resources/{id}/agenda` (turnos en un
rango de fechas, `admin` o `staff`); `/reminders/dispatch` (solo `admin`,
dispara los recordatorios vencidos — 24h y 2h antes de cada turno, fijo);
y `/appointments/{id}/deposit` (pedir/consultar una seña, `admin` o
`staff`) + `/deposits/{id}/mark-paid`/`mark-failed`/`refund` (solo `admin`,
confirma el estado de la seña). El endpoint `/demo/seed` fue reemplazado
por el CRUD.

Recordatorios y señas todavía no tienen un canal real conectado: los
recordatorios se loguean (`LoggingNotificationPort`) y las señas se cobran
y confirman fuera de la app, a mano (`ManualPaymentPort` — ver
`DECISIONS.md` ADR-009).

## Autenticación

Sesión por cookie firmada (`gl_session`), sin API keys ni JWT todavía. Al
arrancar sin usuarios, se crea un admin de bootstrap
(`GESTIOLIBRA_ADMIN_USERNAME`/`GESTIOLIBRA_ADMIN_PASSWORD`; sin contraseña
configurada la app no levanta salvo `ENV=development`, donde usa
`admin`/`admin`). Roles: `admin` (todo) y `staff` (solo `/appointments` y
`/resources/{id}/agenda`).

Gestiolibra posee la API HTTP y el flujo de producto. LibraGenda permanece
como paquete reutilizable, con sus propias migraciones (no se distribuyen
en el wheel de pip; ver más abajo).

## Base de datos

**SQLite es el destino de producción por defecto**, mismo estándar que
toda la familia Libra (arquitectura silo: una instancia/base aislada por
cliente, igual que Contalibra/Restolibra — ver `DECISIONS.md` ADR-010).
`LibraGenda.configure(url)` activa `PRAGMA foreign_keys=ON`
automáticamente para cualquier conexión SQLite. PostgreSQL sigue
soportado vía la misma `DATABASE_URL` para el caso puntual que lo
amerite, sin cambios de código.

Facturación/caja usa `libracore.db` — sqlite3 crudo con su propia
conexión, configurada aparte del engine SQLAlchemy de LibraGenda/
Gestiolibra vía `GESTIOLIBRA_LIBRACORE_DB_PATH` (default
`./data/gestiolibra_libracore.db`, mismo criterio de volumen persistente
que el resto de los paths de datos). Ver `DECISIONS.md` ADR-011.

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
`pyproject.toml` (hoy `v0.6.0`):

```bash
LIBRAGENDA_REF=v0.6.0 DATABASE_URL="sqlite:///data/gestiolibra.db" \
  bash path/a/libragenda/scripts/run_migrations.sh
```

**2. Migraciones propias de Gestiolibra** (`users`, `branch_contacts`,
`branch_hours`, `service_prices`, `business_settings` — no pertenecen al
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

## CI

`.github/workflows/ci.yml`: en cada push/PR a `main` — instala el paquete,
corre `pytest`, y como smoke check aplica las dos cadenas de Alembic
(LibraGenda + propia) contra un archivo SQLite, mismo orden que un deploy
real. Sin servicio de base de datos que levantar — SQLite es un archivo.

**Requiere un secret `LIBRA_PAT`** en este repo (Settings → Secrets and
variables → Actions): `libragenda` y `libracore` son privados, y el
`GITHUB_TOKEN` automático de Actions no tiene acceso a otros repos. Crear
un fine-grained PAT en <https://github.com/settings/tokens?type=beta>
scoped **solo** a `libragenda` y `libracore`, permiso **Contents:
Read-only**, y cargarlo como ese secret. Sin este secret, el paso "Install
package + dev deps" falla (no un bug del workflow).

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

Las migraciones de LibraGenda y las propias deben aplicarse (`alembic
upgrade head` en ambas cadenas) antes de iniciar la aplicación real.

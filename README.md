# Gestiolibra

Vertical de gestión de turnos para negocios de servicios no clínicos:
barberías, peluquerías, estética, lavaderos, talleres y similares.

Compone:

- LibraGenda `v0.9.0` — agenda, recursos, servicios, ciclo de vida de turnos
  (incluye `complete()`), disponibilidad/bloqueos/excepciones, feriados y
  timezone por sucursal, recurrencias, recordatorios (puerto de
  notificaciones + `list_sent()` para reportes), señas (puerto de pagos,
  `medio_pago` opcional + `list_by_status()`) y motivo opcional de
  cancelación/reprogramación.
- LibraCore `v0.16.1` — `libracore.auth.SessionAuth` (login por cookie
  firmada) y `libracore.arca_facturacion`/`libracore.db` (facturación
  electrónica ARCA + caja, ver `DECISIONS.md` ADR-011).

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
`pyproject.toml` (hoy `v0.9.0`):

```bash
LIBRAGENDA_REF=v0.9.0 DATABASE_URL="sqlite:///data/gestiolibra.db" \
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

## Planes y módulos

Onboarding multi-negocio con enforcement real (ver `DECISIONS.md` ADR-013).
`plans.py` (raíz del repo) define tres planes — Básico ($15k), Estándar
($25k) y Premium ($40k) — y qué módulos gateables incluye cada uno.
Catálogo y turnos son siempre gratis y nunca se gatean; lo que varía por
plan es recordatorios, señas, facturación y dashboard.

La tabla `modulos` (migración `0005_modulos`) guarda el estado real por
instancia — se siembra con todo habilitado por defecto (una instancia sin
plan asignado no bloquea nada) y `aplicar_plan_en_db()` la ajusta cuando
se asigna un plan real. `require_module(nombre)` (`app/modules_gate.py`)
devuelve 403 en los routers gateados si el módulo está deshabilitado;
completar un turno (`POST /appointments/{id}/complete`) nunca se bloquea
por plan — si "facturacion" está deshabilitado simplemente no factura.

## Deploy

Primera infraestructura de deploy de Gestiolibra (`Dockerfile`,
`docker-compose.yml`, `app/asgi.py`, `scripts/{nuevo_cliente,panel_admin,
npm_api,npm_setup}.py`) — mismo patrón que Contalibra/Restolibra
(silo: una instancia + una base SQLite aislada por cliente, ver
`DECISIONS.md` ADR-010/ADR-013), usando `libracore.provisioning` como
motor genérico de alta de clientes.

**Particularidad de Gestiolibra**: compone dos paquetes privados
(LibraGenda y LibraCore) en lugar de uno solo, así que el build de Docker
necesita autenticarse contra **dos repos** por SSH en el mismo paso
(`RUN --mount=type=ssh`). `pyproject.toml` usa `git+https://` para ambas
dependencias (necesario para el dev local en WSL, sin identidad SSH
propia contra GitHub); el `Dockerfile` reescribe esas URLs a
`ssh://git@github.com/` solo durante el build
(`git config --global url."ssh://...".insteadOf "https://github.com/"`),
sin tocar `pyproject.toml`.

En el VPS esto requiere un `ssh-agent` persistente con **ambas** claves
cargadas (el deploy key de LibraCore ya existente más uno nuevo
de solo lectura para LibraGenda, `id_ed25519_libragenda`):

```bash
ssh-agent -a /root/.ssh/agent-multi-libra.sock > /root/.ssh/agent-multi-libra.env
SSH_AUTH_SOCK=/root/.ssh/agent-multi-libra.sock ssh-add ~/.ssh/id_ed25519_libracore
SSH_AUTH_SOCK=/root/.ssh/agent-multi-libra.sock ssh-add ~/.ssh/id_ed25519_libragenda
```

Y pasar ese socket como `LIBRACORE_SSH_KEY` al invocar
`scripts/panel_admin.py` (que delega en
`libracore.provisioning.panel_admin.cmd_actualizar`, hoy con un único
`--ssh default=<...>` hardcodeado — ver limitación documentada en
`TASKS.md`):

```bash
LIBRACORE_SSH_KEY=/root/.ssh/agent-multi-libra.sock python3 scripts/panel_admin.py actualizar <cliente>
```

`docker-compose.yml` levanta `gestiolibra-dev` en el puerto `8075`
(puerto base para clientes reales vía provisioning: `8076`). Expuesto
además en `https://dev.gestiolibra.com.ar` (proxy NPM + certificado
Let's Encrypt real, mismo patrón que `dev.contalibra.com.ar` — ver
`DECISIONS.md` ADR-016). `scripts/npm_api.py`/`npm_setup.py` (wrappers
sobre `libracore.npm_api`/`libracore.provisioning`) arman el proxy +
certificado por dominio; reutilizan la misma instancia de NPM y
credenciales que ya usan Contalibra/Restolibra (config en
`scripts/.npm_config.json`, gitignoreado).

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
DATABASE_URL="sqlite:///./dev-data/gestiolibra.db" uvicorn app.asgi:app --reload
```

`app/asgi.py` es el entrypoint que usa uvicorn en contenedor (Docker) o
local — lee `DATABASE_URL` del entorno una sola vez al importar, porque
`create_app()` requiere ese argumento y no puede usarse directo como
factory de uvicorn. Las migraciones de LibraGenda y las propias deben
aplicarse (`alembic upgrade head` en ambas cadenas) antes de iniciar la
aplicación real.

## Frontend

Primer frontend de Gestiolibra (ver `DECISIONS.md` ADR-019): SPA en
React + TypeScript + Vite, en `frontend/`. Páginas: `/agenda` (login +
turnos, MVP original), `/clientes`, `/reportes` (dashboard, admin-only)
y `/facturacion` (admin-only — config ARCA; completar un turno con
saldo pendiente pide el medio de pago y muestra la factura emitida, ver
`DECISIONS.md` ADR-027). Consume la API JSON de este mismo repo sin
cambios — misma cookie de sesión (`gl_session`).

```bash
cd frontend
npm install
npm run dev       # servidor de dev en http://localhost:5173
```

El backend FastAPI (`uvicorn app.asgi:app --reload`) tiene que estar
corriendo en el puerto 8000 al mismo tiempo — `vite.config.ts` proxea
los prefijos de la API (`/auth`, `/branches`, `/appointments`, etc.) al
backend, así todo queda en el mismo origen (`localhost:5173`) y la
cookie de sesión funciona sin pelear con CORS/`SameSite` cross-origin.

En producción no hay un segundo contenedor: el `Dockerfile` tiene un
stage de build con `node:20-slim` que corre `npm run build`, y la
imagen final de Python solo copia el resultado (`frontend/dist`).
`app/asgi.py` sirve esos estáticos desde el mismo proceso FastAPI —
`/assets` como archivos estáticos y una ruta catch-all que devuelve
`index.html` para cualquier path no reconocido por la API, así el
routing del lado del cliente (`react-router-dom`) funciona en cualquier
URL. Si `frontend/dist` no existe (por ejemplo, corriendo `uvicorn
app.asgi:app` local sin haber buildeado el frontend), el mount se salta
solo y la app sigue funcionando como API pura.

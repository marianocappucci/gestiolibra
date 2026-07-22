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
  turnos del recurso por rango de fechas. `cancel()`/`reschedule()` delegan
  en el `reason` opcional que LibraGenda `v0.5.0` agregó al motor —
  Gestiolibra no valida ni interpreta el contenido, solo lo pasa.
- `app/routers/`: `health.py` (público), `auth.py` (`/auth/login`,
  `/auth/logout`, `/auth/me`), `users.py` (CRUD de usuarios, admin-only),
  `branches.py`, `resources.py`, `services.py`, `clients.py` (CRUD completo
  — create/list/get/update/delete — sobre `SqlAlchemyCatalogRepository` de
  LibraGenda), `availability.py` (CRUD de ventanas/bloqueos/excepciones por
  recurso sobre `SqlAlchemyAvailabilityRepository`), `appointments.py`
  (crear, confirmar, cancelar y reprogramar — los dos últimos con `reason`
  opcional en el body), `agenda.py` — traducen excepciones de dominio y
  `IntegrityError`/`KeyError` a códigos HTTP (404/409/422). Reemplazó al
  `/demo/seed` placeholder.
- `app/auth.py`: reusa `libracore.auth.SessionAuth` (cookie firmada, ya
  probada en producción por Contalibra/Restolibra) para la mecánica de
  sesión — pero define sus propias dependencias FastAPI (`get_current_user`,
  `require_role`) que devuelven 401/403 JSON en vez de los redirects 307 a
  `/login` que trae `SessionAuth.require_auth`/`require_role` (pensados
  para una app server-rendered, no para esta API JSON pura).
- `app/security.py`: hashing de contraseñas PBKDF2 (260k iteraciones, salt
  por password, comparación constante contra un hash señuelo) — mismo
  algoritmo que `libracore.db.usuarios`, reimplementado porque ese módulo
  está acoplado a SQLite vía `libracore.db.core.get_connection` y
  Gestiolibra usa PostgreSQL/SQLAlchemy.
- `app/services/users.py`: `UserRow` (tabla propia de Gestiolibra, no del
  dominio de LibraGenda) + `UserRepository` (CRUD + `check_credentials` con
  el mismo patrón de tiempo constante contra un hash señuelo) +
  `ensure_default_admin()` (bootstrap del primer admin al arrancar, mismo
  criterio fail-closed que `SECRET_KEY`: sin `GESTIOLIBRA_ADMIN_PASSWORD`
  configurado la app no levanta, salvo `ENV=development`).
- Roles: `admin` (CRUD completo — catálogo, disponibilidad, usuarios) y
  `staff` (solo `/appointments` y `/resources/{id}/agenda` — su propia
  agenda de turnos, sin tocar catálogo ni usuarios). Gating centralizado en
  `app/main.py` vía `dependencies=[Depends(require_admin)]`/
  `require_staff` al montar cada router, no repetido por endpoint.

## MVP (pendiente)

- `business`: configuración comercial más allá del CRUD básico de sucursales.
- `billing` (opcional): composición de LibraCore para facturación/caja.

## Después del MVP

- Recordatorios y preferencias de comunicación.
- Señas y políticas de cancelación.
- Dashboard y reportes operativos.

## Fuera de alcance

Historia clínica, recetas, estudios, mesas, comandas, cocina y food cost.

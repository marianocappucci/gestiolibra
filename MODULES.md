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
  `branches.py` (CRUD de sucursales, incluye teléfono/dirección),
  `branch_hours.py` (`/branches/{id}/hours` — horario comercial por
  sucursal), `resources.py`, `services.py`, `service_prices.py`
  (`/services/{id}/prices` — precio por servicio y sucursal),
  `business_settings.py` (`/business` — nombre comercial y moneda,
  singleton), `clients.py` (CRUD completo — create/list/get/update/delete
  — sobre `SqlAlchemyCatalogRepository` de LibraGenda), `availability.py`
  (CRUD de ventanas/bloqueos/excepciones por recurso sobre
  `SqlAlchemyAvailabilityRepository`), `appointments.py` (crear, confirmar,
  cancelar y reprogramar — los dos últimos con `reason` opcional en el
  body; `create`/`reschedule` validan además el horario comercial de la
  sucursal del recurso, si está configurado), `agenda.py` — traducen
  excepciones de dominio y `IntegrityError`/`KeyError` a códigos HTTP
  (404/409/422). Reemplazó al `/demo/seed` placeholder.
- `app/services/branches.py`: `BranchRepository` — coordina el `Branch`
  genérico de LibraGenda con una extensión propia de Gestiolibra
  (`BranchContactRow`: `phone`, `address`), mismo patrón que `Patient`
  extiende `Client` en MedLibra.
- `app/services/branch_hours.py`: `BranchHoursRepository` — horario
  comercial semanal por sucursal. **Opt-in**: una sucursal sin horario
  configurado no gatea nada (mismo comportamiento que siempre hubo); solo
  al configurarlo empieza a exigirse además de la disponibilidad del
  recurso. No es dominio de LibraGenda — el motor solo conoce
  disponibilidad por recurso, no horario "del negocio" a nivel sucursal.
- `app/services/service_prices.py`: `ServicePriceRepository` — precio por
  par (servicio, sucursal), no un precio único en `Service` (LibraGenda no
  conoce precios por diseño, mismo principio que señas/`Deposit`).
- `app/services/business_settings.py`: `BusinessSettingsRepository` —
  configuración global del negocio (nombre comercial, moneda), fila única
  (`id` fijo), no hay multi-tenant de "varios negocios" en un mismo deploy.
- `app/notifications.py`: `LoggingNotificationPort` — implementación
  placeholder del `NotificationPort` de LibraGenda; loguea en vez de
  enviar de verdad (sin proveedor de email/SMS/WhatsApp configurado
  todavía). `DEFAULT_REMINDER_POLICIES` fija dos avisos (24h y 2h antes),
  no configurable por sucursal/servicio por ahora.
- `app/payments.py`: `ManualPaymentPort` — implementación placeholder del
  `PaymentPort` de LibraGenda; `request_charge`/`request_refund` no cobran
  solos, solo loguean la intención. La confirmación real de pago es manual
  (`POST /deposits/{id}/mark-paid`, admin-only) hasta que se resuelva la
  decisión de facturación/MercadoPago (`libracore.mp_api`).
- `app/routers/reminders.py`: `POST /reminders/dispatch` (admin-only) —
  dispara `ReminderDispatcher.dispatch()` de LibraGenda con `now` actual;
  pensado para un cron/scheduler externo (no configurado en este repo).
- `app/routers/deposits.py`: `POST`/`GET /appointments/{id}/deposit`
  (admin+staff, parte del flujo de reserva) y
  `POST /deposits/{id}/mark-paid`/`mark-failed`/`refund` (admin-only,
  confirmación de dinero). Envuelve `DepositManager` de LibraGenda.
- `app/auth.py`: reusa `libracore.auth.SessionAuth` (cookie firmada, ya
  probada en producción por Contalibra/Restolibra) para la mecánica de
  sesión — pero define sus propias dependencias FastAPI (`get_current_user`,
  `require_role`) que devuelven 401/403 JSON en vez de los redirects 307 a
  `/login` que trae `SessionAuth.require_auth`/`require_role` (pensados
  para una app server-rendered, no para esta API JSON pura).
- `app/security.py`: hashing de contraseñas PBKDF2 (260k iteraciones, salt
  por password, comparación constante contra un hash señuelo) — mismo
  algoritmo que `libracore.db.usuarios`, reimplementado en vez de importar
  las funciones privadas (prefijo `_`) de ese módulo, no pensado para
  reuso directo (razón que se sostiene aunque ambos usen SQLite hoy — ver
  `DECISIONS.md` ADR-005/ADR-010).
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

- `billing` (opcional): composición de LibraCore para facturación/caja.

## Después del MVP

- Canal real de notificaciones (email/SMS/WhatsApp) para reemplazar
  `LoggingNotificationPort`.
- Proveedor de pago real (MercadoPago u otro) para reemplazar
  `ManualPaymentPort` y automatizar la confirmación de señas.
- Dashboard y reportes operativos.

## Fuera de alcance

Historia clínica, recetas, estudios, mesas, comandas, cocina y food cost.

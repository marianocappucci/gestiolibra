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
  — sobre `ClientRepository`, incluye `cuit`/`condicion_iva` desde
  ADR-011), `availability.py`
  (CRUD de ventanas/bloqueos/excepciones por recurso sobre
  `SqlAlchemyAvailabilityRepository`), `appointments.py` (crear, confirmar,
  cancelar, reprogramar y **completar** — los dos de en medio con `reason`
  opcional en el body; `create`/`reschedule` validan además el horario
  comercial de la sucursal del recurso, si está configurado; `complete`
  factura con LibraCore si el servicio tiene precio configurado, ver
  ADR-011), `billing.py` (`/config/arca`, admin-only), `dashboard.py`
  (`GET /dashboard?date_from=&date_to=`, admin-only), `agenda.py` —
  traducen excepciones de dominio y `IntegrityError`/`KeyError` a códigos
  HTTP (404/409/422). Reemplazó al `/demo/seed` placeholder.
- `app/services/branches.py`: `BranchRepository` — coordina el `Branch`
  genérico de LibraGenda con una extensión propia de Gestiolibra
  (`BranchContactRow`: `phone`, `address`), mismo patrón que `Patient`
  extiende `Client` en MedLibra.
- `app/services/clients.py`: `ClientRepository` — coordina el `Client`
  genérico de LibraGenda con `client_billing` (`cuit`, `condicion_iva`),
  extensión propia agregada en ADR-011 para facturación (antes se
  exponía el `Client` de LibraGenda directo, sin ninguna extensión).
  `delete()` borra la extensión antes que el `Client` genérico, mismo
  orden que `BranchRepository`/`PatientRepository` de esta familia.
- `app/services/billing.py`: integración de facturación/caja con
  `libracore.db` (sqlite3 crudo, conexión propia vía
  `libracore.db.core.configure()`, separada del engine SQLAlchemy del
  resto de la app). `configure(path)` asegura el schema compartido y
  una caja por defecto; `get_arca_config()`/`set_arca_config()` — una
  sola "empresa" fija (instancia única por cliente);
  `invoice_appointment()` — una factura por el total del servicio (tipo
  A/B según condición de IVA del cliente vía `arca_facturacion` de
  LibraCore), seña ya cobrada y saldo restante como dos movimientos de
  caja separados apuntando a la misma factura. Mismo diseño exacto que
  MedLibra (ver ADR-011).
- `app/services/dashboard.py`: `DashboardService` — resumen de lectura
  pura sobre repositorios ya existentes, sin tabla ni estado propio.
  Turnos (total y por estado en el rango pedido, turnos de **hoy** —
  fecha real del servidor, no del rango), clientes (total activos vía
  `ClientRepository.count_active()`, altas nuevas en el rango vía
  `count_created_between()`, que lee `client_billing.created_at`), y
  recordatorios enviados en el rango (`SentReminderRepository.
  list_sent()` de LibraGenda `v0.9.0`) + señas pendientes sin acotar
  por fecha (`DepositRepository.list_by_status()`, misma versión).
  Facturación/caja quedó fuera del primer corte (decisión del usuario,
  mismo alcance que MedLibra) — ver `DECISIONS.md` ADR-012 — y se sumó
  después: `facturacion.facturas_emitidas_en_periodo` +
  `facturacion.caja` (ingresos/egresos/saldo del período + saldo total),
  llamando directo a `libracore.db.facturas.get_facturas_filtradas()`/
  `caja.get_caja_resumen()` (misma conexión global que ya configura
  `billing.py`, sin dependencia nueva inyectada) — ver ADR-015.
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
  `mark-paid` acepta `medio_pago` opcional desde LibraGenda `v0.8.0`.
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
- `plans.py` (raíz del repo): `PLANES`/`PLAN_MODULOS`/`PLAN_PRECIOS`
  (Básico/Estándar/Premium) + `aplicar_plan_en_db()`, mismo patrón que
  `plans.py` de Contalibra. Catálogo/turnos siempre gratis; lo gateable
  es recordatorios, señas, facturación y dashboard.
- `app/services/modules.py`: `ModuleRepository` — lee/escribe la tabla
  `modulos` (migración `0005_modulos`). `ensure_seeded()` habilita todo
  por defecto (sin bloquear nada hasta que se asigne un plan real);
  `is_enabled()` trata cualquier módulo fuera de `TODOS_LOS_MODULOS`
  (catálogo/turnos) como siempre habilitado.
- `app/modules_gate.py`: `require_module(nombre)` — dependency factory
  que devuelve 403 si el módulo no está habilitado, mismo patrón que
  `require_role` de `app/auth.py`. Aplicado a routers completos
  (recordatorios/señas/facturación/dashboard); `complete()` de turno lo
  chequea puntualmente para saltar la facturación sin bloquear el turno.
- `Dockerfile`/`docker-compose.yml`/`app/asgi.py`: primera infraestructura
  de deploy de Gestiolibra (nunca se había desplegado). Mismo patrón que
  Contalibra/Restolibra (`--mount=type=ssh` con deploy key dedicada) —
  `pyproject.toml` usa `git+https` para LibraGenda/LibraCore (necesario
  para el dev local en WSL, sin identidad SSH contra GitHub), y el build
  reescribe esas URLs a SSH en tiempo de build. `scripts/nuevo_cliente.py`/
  `panel_admin.py`/`npm_api.py`/`npm_setup.py`: wrappers sobre
  `libracore.provisioning`, mismo patrón que Contalibra/Restolibra.

## Después del MVP

- Canal real de notificaciones (email/SMS/WhatsApp) para reemplazar
  `LoggingNotificationPort`.
- Proveedor de pago real (MercadoPago u otro) para reemplazar
  `ManualPaymentPort` y automatizar la confirmación de señas.
- Dashboard y reportes operativos.

## Fuera de alcance

Historia clínica, recetas, estudios, mesas, comandas, cocina y food cost.

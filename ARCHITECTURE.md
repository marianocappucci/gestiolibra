# Arquitectura — Gestiolibra

## Propósito y límites

Gestiolibra es la API y producto vertical para negocios de servicios no clínicos. Cubre barberías, peluquerías, estética, lavaderos, talleres y negocios similares.

Gestiolibra posee el flujo HTTP y las reglas propias del negocio; LibraGenda aporta el motor genérico de agenda. No se incorporan historia clínica, recetas, estudios, mesas, comandas, cocina ni food cost.

## Componentes

- `app/main.py`: factory FastAPI, configuración y composición de dependencias.
  Aplica el gating por rol a nivel de router (`include_router(..., dependencies=[...])`),
  no por endpoint.
- `app/dependencies.py`: providers que leen el estado de la aplicación.
- `app/auth.py`: sesión por cookie firmada (reusa `libracore.auth.SessionAuth`)
  + dependencias FastAPI propias (`get_current_user`, `require_role`) que
  responden 401/403 JSON — la app no tiene páginas HTML, así que los
  redirects 307 de `SessionAuth.require_auth`/`require_role` no aplican acá.
- `app/security.py`: hashing de contraseñas (PBKDF2, mismo algoritmo que
  `libracore.db.usuarios`, propio porque ese módulo está acoplado a SQLite).
- `app/services/appointments.py`: capa de aplicación sobre LibraGenda.
  `create()`/`reschedule()` validan además el horario comercial de la
  sucursal del recurso (`branch_hours`), cuando está configurado.
- `app/services/users.py`: tabla y repositorio de usuarios propios de
  Gestiolibra (no pertenecen al dominio de LibraGenda).
- `app/services/branches.py`, `branch_hours.py`, `service_prices.py`,
  `business_settings.py`: configuración comercial, todas tablas propias de
  Gestiolibra (no de LibraGenda) — ver "Configuración comercial" abajo.
- `app/notifications.py`, `app/payments.py`: implementaciones placeholder de
  los puertos `NotificationPort`/`PaymentPort` de LibraGenda — ver
  "Recordatorios y señas" abajo.
- `app/routers/`: health (público), auth (login/logout/me), users (admin-only),
  sucursales (+ horario, + contacto), recursos, servicios (+ precio por
  sucursal), clientes, disponibilidad, negocio (`/business`), turnos,
  agenda, recordatorios (`/reminders/dispatch`) y señas (`/appointments/{id}/deposit`,
  `/deposits/{id}/...`).

## Configuración comercial

Tres piezas, todas tablas propias de Gestiolibra (LibraGenda no las conoce
por diseño — no calcula precios ni tiene noción de "horario del negocio" a
nivel sucursal, solo disponibilidad por recurso):

- **Horario comercial** (`branch_hours`): horario semanal por defecto a
  nivel sucursal. **Opt-in**: una sucursal sin horario configurado no
  gatea nada — mismo comportamiento que había antes de esta feature. Una
  vez configurado, se exige además de la disponibilidad propia del
  recurso (intersección, no reemplazo).
- **Precio por servicio y sucursal** (`service_prices`): un mismo servicio
  puede costar distinto en cada sucursal, así que es una tabla
  servicio×sucursal→precio, no un campo único en `Service`.
- **Datos de contacto y del negocio**: teléfono/dirección son por
  sucursal (`branch_contacts`, extensión de `Branch` igual que `Patient`
  extiende `Client` en MedLibra); nombre comercial y moneda son del
  negocio como un todo (`business_settings`, fila única).
## Recordatorios y señas

Ambos ya vienen resueltos como motor de dominio en LibraGenda
(`ReminderDispatcher`/`due_reminders()`, `DepositManager`) — lo que faltaba
en Gestiolibra era conectarlos a un canal real, y todavía no hay uno
elegido (ver ADR-009):

- **Recordatorios**: `LoggingNotificationPort` implementa `NotificationPort`
  logueando en vez de enviar. `DEFAULT_REMINDER_POLICIES` (24h y 2h antes,
  fijo, no configurable por sucursal/servicio) se pasa a `ReminderDispatcher`
  al construir la app. `POST /reminders/dispatch` (admin-only) está pensado
  para un cron/scheduler externo, no hay uno corriendo dentro de este repo.
- **Señas**: `ManualPaymentPort` implementa `PaymentPort`; `request_charge`/
  `request_refund` no cobran ni reintegran solos, solo loguean la
  intención. El dinero se confirma fuera de la app (efectivo, transferencia,
  link de MercadoPago enviado a mano) y un admin lo refleja con
  `POST /deposits/{id}/mark-paid`/`mark-failed`/`refund`.
- Ninguna de las dos piezas necesitó una migración nueva: `deposits` y
  `sent_reminders` son tablas propias de LibraGenda (`0005`/`0006` de su
  propia cadena), no de Gestiolibra.

- `MODULES.md`: inventario operativo de módulos.
- LibraGenda `v0.5.0`: dependencia versionada para dominio, persistencia y migraciones propias.
- LibraCore (sin versión de facturación/caja todavía): dependencia versionada
  solo por `libracore.auth.SessionAuth` — ver `DECISIONS.md` ADR-005.

## Autenticación y roles

Sesión por cookie firmada (`itsdangerous`, vía LibraCore), sin JWT ni
tokens de API todavía. Dos roles: `admin` (catálogo completo, disponibilidad,
usuarios) y `staff` (solo su propia agenda: crear/confirmar/cancelar/
reprogramar turnos). La tabla `users` es de Gestiolibra, no de LibraGenda ni
de LibraCore — cada producto de la familia Libra que reusa `SessionAuth`
trae su propia tabla de usuarios en su propio stack de persistencia (ver
`libracore.auth`'s docstring: callback en vez de asumir el schema).

## Persistencia e integración

La aplicación configura LibraGenda mediante `LIBRAGENDA_DATABASE_URL` y usa PostgreSQL dedicado para Gestiolibra. Dos cadenas de Alembic independientes corren contra la misma base, cada una con su propia tabla de versión: las de LibraGenda (schema del motor, ejecutadas desde el repositorio upstream en el tag exacto pineado) y las propias de Gestiolibra (`migrations/` de este repo — `users`, y desde `0002_business_config` también `branch_contacts`/`branch_hours`/`service_prices`/`business_settings` —, tabla de versión `alembic_version_gestiolibra` para no colisionar con la de LibraGenda). `Base.metadata.create_all()` sigue existiendo en `create_app()` pero solo importa para los tests con SQLite en memoria — en producción es un no-op una vez que ambas cadenas de Alembic ya crearon el schema real.

La lógica de negocio no debe duplicarse localmente cuando pertenece al motor genérico. Los routers traducen errores de dominio e integridad a respuestas HTTP.

## Entornos y deploy

- Desarrollo: entorno dev con base `gestiolibra` y usuario dedicado.
- Demo: producción controlada para validación.
- Producción: dominio del cliente.

La rama observada actualmente es `main`. La adopción de `develop` como rama de integración queda pendiente de una decisión operativa explícita.

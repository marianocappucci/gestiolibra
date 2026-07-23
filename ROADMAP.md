# Roadmap de Gestiolibra

## Fase 0 — scaffold (completa)

Repo privado, FastAPI, dependencia LibraGenda `v0.3.0`, PostgreSQL dedicado
real (base `gestiolibra`, usuario `gestiolibra_dev`, Postgres 16 del VPS
Donweb) migrado con la cadena Alembic completa de LibraGenda (`0001`→`0006`)
y verificado end-to-end con los repositorios SQLAlchemy reales — no solo el
smoke test sqlite del demo. Cierra el ítem "Gestiolibra usa LibraGenda en un
entorno dev real" de la Fase 3 del roadmap de LibraGenda.

## Fase 1 — MVP operativo (completa)

- Separar el demo en routers y servicios de aplicación (completo).
  `app/routers/` (health, demo, appointments) + `app/services/` (
  `AppointmentService`, capa de aplicación sobre `InMemoryScheduler`) +
  `app/dependencies.py`. El endpoint `/demo/seed` queda como placeholder
  explícito hasta que lo reemplace el CRUD real del siguiente ítem. Se
  amplió la cobertura de tests HTTP a las ramas de error (servicio
  inexistente, conflicto de horario, fuera de disponibilidad, turno
  inexistente, doble confirmación) que antes solo se probaban por el
  camino feliz.
- CRUD de sucursales, recursos, servicios y clientes (completo). Routers
  `branches`, `resources`, `services`, `clients` con create/list/get/
  update/delete real, reemplazando el `/demo/seed`. Requirió extender
  `SqlAlchemyCatalogRepository` de LibraGenda (upstream) con `get_x`/
  `update_x`/`delete_x` — solo tenía `add_x`/`list_x`; se corrigió ahí, no
  con un shim local, siguiendo la regla de no duplicar reglas/persistencia
  de LibraGenda (LibraGenda `v0.4.1`, tag patch). Verificado contra la base
  real de Gestiolibra en el VPS, no solo sqlite.
- Agenda diaria/semanal y disponibilidad configurable por negocio
  (completo). `/resources/{id}/availability` (ventanas semanales),
  `/blocks` (bloqueos puntuales), `/exceptions` (excepciones por fecha) —
  CRUD completo sobre `SqlAlchemyAvailabilityRepository` de LibraGenda.
  `/resources/{id}/agenda?date_from=&date_to=` devuelve los turnos del
  recurso en el rango. **Cambio de comportamiento real**: `AppointmentService.create()`
  dejó de usar una ventana 9-18 hardcodeada — ahora lee la disponibilidad
  real configurada (ventanas + bloqueos + excepciones); un recurso sin
  disponibilidad configurada ya no puede recibir turnos (409). Encontró un
  bug real de LibraGenda en el camino: `DateTime(timezone=True)` vuelve
  *naive* en SQLite (sin tipo timestamptz nativo) pero *aware* en
  PostgreSQL — mismo dato, comportamiento distinto por dialecto, invisible
  en dev con sqlite pero rompía comparaciones de intervalos contra la base
  real. Corregido upstream en LibraGenda (`ensure_utc()` en las
  conversiones fila→dominio, tag `v0.4.2`) — otra vez el mismo patrón:
  arreglar en el motor, no con un workaround local.
- Cancelar y reprogramar con motivos (completo). `POST /appointments/{id}/cancel`
  y `POST /appointments/{id}/reschedule`, ambos con `reason` opcional en el
  body, usando el campo que LibraGenda agregó en `v0.5.0` para exactamente
  este caso (Gestiolibra y MedLibra lo tenían pendiente en paralelo).
- Login y roles básicos (completo). Reusa `libracore.auth.SessionAuth`
  (cookie firmada, ya probada en producción por Contalibra/Restolibra) para
  la mecánica de sesión, con tabla `users` propia (SQLAlchemy/PostgreSQL,
  no la de LibraCore que es SQLite) y dos roles: `admin` (todo el catálogo,
  disponibilidad y usuarios) y `staff` (solo su propia agenda de turnos).
  Gating centralizado al montar los routers en `app/main.py`, no repetido
  por endpoint. Suma `libracore` como dependencia nueva de Gestiolibra.

## Fase 2 — operación comercial (completa)

- Configuración comercial del negocio (completo). Tres piezas, alcance
  acordado con el usuario antes de codificar: (1) horario comercial por
  sucursal (`branch_hours`, opt-in — sin configurar no gatea nada, igual
  que hasta ahora; configurado, se exige además de la disponibilidad del
  recurso); (2) precio por servicio y sucursal (`service_prices`, no un
  precio único en `Service` — LibraGenda no conoce precios por diseño);
  (3) datos de contacto por sucursal (`branch_contacts`: teléfono,
  dirección) y datos globales del negocio (`business_settings`: nombre
  comercial, moneda). Cuatro tablas nuevas, migración `0002_business_config`
  en el Alembic propio de Gestiolibra. `AppointmentService.create()`/
  `reschedule()` validan el horario comercial cuando está configurado.
- Recordatorios y señas (completo). `POST /reminders/dispatch` (admin-only)
  dispara los avisos vencidos (24h y 2h antes, fijo por ahora) sobre
  `ReminderDispatcher` de LibraGenda; `POST`/`GET /appointments/{id}/deposit`
  (admin+staff) y `POST /deposits/{id}/mark-paid`/`mark-failed`/`refund`
  (admin-only) sobre `DepositManager` de LibraGenda. Decisión acordada con
  el usuario antes de codificar: sin proveedor de notificaciones ni de pago
  todavía, así que ambos puertos de LibraGenda (`NotificationPort`,
  `PaymentPort`) se implementan como placeholders — `LoggingNotificationPort`
  solo loguea, `ManualPaymentPort` no cobra solo, la confirmación de señas
  es manual por admin. No hizo falta migración nueva: `deposits` y
  `sent_reminders` son tablas propias de LibraGenda, ya migradas por su
  propia cadena (`0005`/`0006`). Reemplazar ambos puertos por integraciones
  reales queda para "Después del MVP" (ver `MODULES.md`).
- Caja/facturación componiendo LibraCore (completo). Mismo diseño exacto
  que MedLibra (ver ADR-011 y `DECISIONS.md` de ese repo, ADR-016):
  `client_billing` extiende `Client` con `cuit`/`condicion_iva` (primera
  extensión propia de Client — antes se usaba el genérico de LibraGenda
  sin extensión), config ARCA de instancia única (`PUT`/
  `GET /config/arca`), `POST /appointments/{id}/complete` factura el
  turno completo con `libracore.arca_facturacion` cuando el servicio
  tiene precio configurado — una sola factura (tipo A/B según condición
  de IVA), seña y saldo como movimientos de caja separados sobre la
  misma factura. `libragenda` a `v0.8.0`, `libracore` a `v0.16.1`.
- Dashboard (completo). Mismo alcance que MedLibra (`AskUserQuestion`:
  mismo diseño) en el primer corte: turnos (total y por estado en un
  rango, turnos de hoy), clientes (total activos, altas nuevas en el
  rango) y recordatorios enviados/señas pendientes — facturación/caja
  quedó fuera de ese corte y se sumó después (ver ADR-015).
  `GET /dashboard?date_from=&date_to=`
  (admin-only), puro de lectura sobre repositorios ya existentes más
  `SentReminderRepository.list_sent()`/`DepositRepository.
  list_by_status()` de LibraGenda `v0.9.0`. Ver `DECISIONS.md` ADR-012.

## Fase 3 — producto

- Onboarding multi-negocio (completo — ver ADR-013). Sistema de planes
  con enforcement real (Básico/Estándar/Premium, `plans.py` + tabla
  `modulos`, `require_module()` gatea recordatorios/señas/facturación/
  dashboard con 403 — turnos y catálogo nunca se gatean). Primera
  infraestructura de deploy de Gestiolibra (Dockerfile, docker-compose.yml,
  `scripts/nuevo_cliente.py`/`panel_admin.py`/`npm_api.py`/`npm_setup.py`,
  wrappers sobre `libracore.provisioning`, mismo patrón que Contalibra/
  Restolibra). Deploy key nueva de solo lectura para LibraGenda + ssh-agent
  persistente en el VPS con ambas claves (Gestiolibra es el primer
  producto que necesita dos deploy keys a la vez en el mismo build).
  Build real y primer cliente de prueba verificados en el VPS — dos bugs
  reales encontrados y corregidos en el proceso (auth SSH multi-key,
  contrato de env vars de `libracore.provisioning`), ver `TASKS.md`.
- Branding y dominio por cliente (completo — ver ADR-016/ADR-017).
  "Branding" más allá de dominio+SSL no aplica: Gestiolibra no tiene
  frontend, y el logo/paleta por producto de Contalibra/Restolibra no es
  configurable por cliente. `dev.gestiolibra.com.ar` con proxy NPM +
  certificado Let's Encrypt real (reutilizando la misma instancia de NPM
  de Contalibra/Restolibra, sin credenciales nuevas). El flujo automático
  de alta (`_setup_npm_proxy()` de `libracore.provisioning`, el mismo que
  usaría un cliente real) se probó de punta a punta contra el cliente
  `prueba` (`prueba.gestiolibra.com.ar`) una vez corregido el
  `forward_host` — confirmado que no era un bug de la librería, sino un
  valor de configuración copiado mal desde Contalibra.
- Deploy dev/prod, CI y backups verificados (completo). Deploy real y CI
  ya verificados desde el onboarding multi-negocio. Backups: `panel_admin.py
  backup`/`restore-db` probados de punta a punta contra el cliente
  `prueba` (fila marcadora → backup → mutación → restore → confirmado
  que vuelve el dato original) — ver ADR-017.
- Validación con primeros negocios reales — el único ítem que no se
  puede cerrar con trabajo de ingeniería: necesita un negocio real
  usando el producto, y hoy solo hay una API JSON sin frontend (ver
  `wiki/entities/gestiolibra.md` de la wiki del ecosistema). Queda
  abierto hasta que haya un cliente real o se decida construir una
  interfaz.

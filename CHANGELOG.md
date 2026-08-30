# Changelog — Gestiolibra

## [Unreleased]

- **La pantalla dice de qué ambiente es el token de MercadoPago**: `Ambiente de
  prueba`, `Ambiente de producción` o `Ambiente sin verificar`, con la fecha en
  que se determinó. 🔴 MercadoPago **no tiene homologación como ARCA** — no hay
  host de sandbox, es el mismo `api.mercadopago.com` y lo que define el ambiente
  es el token. Sin el cartel las dos fallas son mudas: un token de producción en
  una instancia `dev` **cobra plata de verdad** y uno de prueba en la instancia
  de un cliente **no cobra nada**, y las dos se ven igual. Mirar el prefijo no
  alcanza, porque un *usuario de prueba* de MercadoPago entrega credenciales
  `APP_USR-` igual que las reales: lo único que lo delata es el `nickname` de
  `/users/me`, así que quien clasifica es **Probar conexión**, que ahora recarga
  la sección. La clasificación lleva la huella del token, así que si la
  credencial cambia por cualquier vía se descarta sola. Pines: `libracore`
  v1.63.0 → v1.65.0 y `libra-ui` v0.49.0 → v0.54.0.
- **La agenda como calendario, y la parametrización adentro de
  Configuración** (ver ADR-031): la agenda pasa de formulario + tabla a
  calendario con vistas de día, semana y mes, consumido de
  `libra-ui/agenda` v0.38.0 (extraído de LibraDesk, no copiado). El estado
  de la pantalla vive en la URL (`?vista=`, `?dia=`, `?recurso=`,
  `?turno=`). Y tres secciones nuevas de Configuración —Sucursales (con su
  horario de atención), Servicios (duración y honorarios por sucursal) y
  Recursos (disponibilidad, bloqueos y excepciones)— que cierran el pedido
  *"no se puede parametrizar servicios, horarios de esos servicios,
  honorarios de esos servicios"*: los endpoints existían desde el MVP, la
  pantalla no. 23 tests nuevos (36 en total).
- **La validación del turno corre en hora de pared** (ver ADR-030):
  arregla el defecto reportado *"El horario elegido está fuera del horario
  de atención"*, que con UTC-3 rechazaba **todo turno que empezara después
  de las 16** en una sucursal abierta de 9 a 19. La disponibilidad, el
  horario comercial y las excepciones se cargan en hora de pared y se
  comparaban contra la hora UTC del turno. Ahora la validación entera
  corre en hora local (`app/services/husos.py` y `_TurnosEnHoraLocal`) y
  la conversión a instante pasa al repositorio. Arrastra otros dos
  síntomas del mismo defecto: los turnos de 21:00 en adelante, que cruzan
  la medianoche UTC y eran irrechazables, y los que se guardaban bien pero
  no aparecían en su día al listar la agenda. Los bloqueos de recurso se
  convierten en el borde de su router. El huso por defecto de una sucursal
  nueva pasa de `UTC` a `America/Argentina/Buenos_Aires`. 5 tests nuevos
  (246 en total).
- **`DOCS_AUTH_SECRET` expuesto en `docker-compose.yml`**: conecta el
  endpoint `POST /auth/verify` (ver abajo) con el valor real cargado en
  `.env`, necesario para que `/docs/` de `gestiolibra_web` autentique
  contra esta instancia. Sin cambios de código.
- **Endpoint `POST /auth/verify`** (ver ADR-029): chequeo de credenciales
  sin sesión, protegido por `X-Internal-Auth`/`DOCS_AUTH_SECRET`, para que
  el login de `/docs/` de `gestiolibra_web` valide contra la instancia
  real del cliente. 5 tests nuevos.
- **Timezone de sucursal de punta a punta** (ver ADR-028):
  `AppointmentService._resolve_utc()` interpreta un horario naive del
  formulario de turno como hora local de la sucursal del recurso (en
  vez de tratarlo como UTC directo), usando
  `libragenda.timezones.to_utc()` (ya existía, nunca conectado).
  `Agenda.tsx` muestra `Horario (<timezone>)` en el formulario y
  formatea los horarios guardados con la timezone de la sucursal, no
  la del navegador. 2 tests nuevos (138 en total). Verificado en
  `dev.gestiolibra.com.ar` real de punta a punta. Con esto, el
  contenido completo de la Fase 4 queda cerrado.
- **Facturación en el frontend: config ARCA + factura al completar un
  turno** (ver ADR-027): página `/facturacion` (admin-only) para
  `GET`/`PUT /config/arca`. Completar un turno con saldo pendiente
  ahora pide el medio de pago en un diálogo en vez de fallar con un
  422 crudo; si la respuesta incluye una factura, se muestra en un
  segundo diálogo (tipo, número, CAE, total). Componente
  `ui/dialog.tsx` nuevo (mismo patrón que `sheet.tsx` sobre
  `radix-ui`). Verificado en `dev.gestiolibra.com.ar` real de punta a
  punta. Sin cambios de backend. 136 tests de backend sin cambios.
- **Stack de frontend normalizado: TanStack Table + React Hook Form +
  Zod** (ver ADR-026): `src/components/data-table.tsx` nuevo (wrapper
  genérico y reutilizable sobre TanStack Table + primitivos shadcn),
  usado en Agenda y Clientes con sorting real por columna. Formularios
  de alta/edición de cliente y de turno migrados a React Hook Form +
  schemas Zod (`clientSchema`, `appointmentSchema`) vía el componente
  `Form` de shadcn — validación declarativa por campo, mismos payloads
  que antes. Verificado manualmente en el browser (errores de
  validación, sorting, altas exitosas). 136 tests de backend sin
  cambios.
- **Rediseño visual del frontend: Tailwind CSS + shadcn/ui** (ver
  ADR-025): sidebar de navegación colapsable reemplaza el nav superior,
  cards con sombra, tablas y badges de estado, avatar con iniciales.
  Mismo comportamiento y llamadas a la API — cambio puramente visual,
  sin tocar el backend. Verificado manualmente en el browser (estilos
  reales confirmados por `getComputedStyle`, sidebar interactivo, sin
  errores de consola en las tres páginas). 136 tests de backend sin
  cambios.
- **El id de cliente se genera solo si no se manda** (ver ADR-024):
  `POST /clients` acepta `id` opcional, generado con `uuid4()` cuando
  se omite. El formulario de alta del frontend ya no pide un ID a
  mano — fricción real que no existía para sucursales/recursos/
  servicios (catálogo armado una vez por un admin, no en la operación
  diaria). 1 test nuevo (136 en total).
- **Fix: ruta `/dashboard` del frontend colisionaba con la API**
  (ver ADR-023): navegación directa (F5, URL a mano) a `/dashboard`
  devolvía el error crudo del endpoint `GET /dashboard` en vez de la
  SPA, porque frontend y API comparten origen y espacio de rutas sin
  prefijo. Renombrada la ruta del frontend a `/reportes` (el endpoint
  de la API no cambia). Solo se nota con carga de página completa, no
  con navegación por el nav (por eso no se vio al verificar ADR-021).
- **Fix real: el frontend quedaba congelado en el primer build**
  (ver ADR-022): el volumen anónimo de ADR-020 (pensado para que el
  bind mount de dev no tapara `frontend/dist`) solo siembra desde la
  imagen la primera vez que se crea — cualquier rebuild posterior
  seguía sirviendo el build viejo sin avisar. `Dockerfile` ahora hornea
  el build en `/opt/frontend-dist`, fuera del árbol bind-monteado;
  `app/asgi.py` lo busca ahí primero. Encontrado porque el usuario
  reportó que el sitio no reflejaba las páginas de Clientes/Dashboard
  recién agregadas.
- **Frontend: páginas de Clientes y Dashboard** (ver ADR-021): extiende
  el MVP de login+agenda. Clientes (lista para staff+admin, alta/
  edición/baja solo admin, reflejando el gating ya existente en la
  API) y Dashboard (mismo resumen que expone `GET /dashboard`, oculto
  del nav para staff). `src/components/Layout.tsx` nuevo (header +
  nav compartidos, antes vivía solo en la página de agenda). Verificado
  manualmente en el browser con ambos roles, sin errores de consola.
  Sin cambios de backend.
- **Frontend desplegado en `dev.gestiolibra.com.ar`** (ver ADR-020):
  primer build real de Docker con el stage de node — encontró que el
  bind mount de dev (`./:/app`) tapaba el `frontend/dist` horneado en
  la imagen con el directorio vacío del host, sirviendo 404 en
  cualquier ruta no-API. Corregido con un volumen anónimo específico
  para ese subpath en `docker-compose.yml`. Verificado con `curl` y en
  el browser real contra el dominio público.
- **Frontend: SPA en React+Vite, MVP de login + agenda** (ver ADR-019):
  primer frontend de Gestiolibra (`frontend/`), nunca antes existió
  ninguno. Login + vista de agenda por recurso/rango de fechas, alta de
  turno, confirmar/cancelar/completar. Consume la API JSON existente sin
  cambios (cookie de sesión, proxy de Vite en dev, servido desde el
  mismo proceso FastAPI en producción vía `app/asgi.py`). Dockerfile con
  stage nuevo de build de node. Verificado manualmente end-to-end en el
  browser (login admin y staff, alta y ciclo de vida completo de un
  turno, sin errores de consola).
- **Lectura de catálogo abierta a staff** (ver ADR-018):
  `branches`/`resources`/`services`/`clients` pasan de admin-only a
  staff+admin en sus endpoints `GET` (escritura sigue admin-only) —
  necesario para que el frontend funcione también logueado como staff,
  no solo admin. 4 tests nuevos (135 en total).
- **Cierre de Fase 3** (ver ADR-017): flujo automático de dominio+SSL
  verificado de punta a punta contra el cliente `prueba`
  (`_setup_npm_proxy()` real, sin workaround — confirma que el hallazgo
  de ADR-016 era config, no bug) y backups probados end-to-end
  (`panel_admin.py backup`/`restore-db`). Sin cambios de código. El
  cuarto ítem de Fase 3 ("validación con primeros negocios reales")
  queda explícitamente abierto — depende de tener un cliente real.
- **Branding y dominio por cliente** (ver ADR-016): `dev.gestiolibra.com.ar`
  con proxy NPM + certificado Let's Encrypt real, reutilizando la misma
  instancia de NPM y credenciales que ya usan Contalibra/Restolibra. Sin
  cambios de código — la maquinaria (`scripts/npm_api.py`/`npm_setup.py`)
  ya existía. "Branding" más allá de dominio+SSL no aplica sin frontend.
- **Dashboard: sumar facturación/caja** (ver ADR-015): `GET /dashboard`
  ahora incluye `facturacion.facturas_emitidas_en_periodo` y
  `facturacion.caja` (ingresos/egresos/saldo del período + saldo total),
  reutilizando `libracore.db.caja.get_caja_resumen()`/`facturas.
  get_facturas_filtradas()`, ya genéricos. 1 test nuevo (131 en total).
- **Deploy real verificado en el VPS** (cierra el onboarding
  multi-negocio de ADR-013, ver ADR-014): build de `gestiolibra:latest`
  y primer cliente de prueba (`prueba`, puerto 8076, plan Premium)
  provisionados con éxito. Dos bugs reales encontrados y corregidos —
  ninguno visible en desarrollo local, sin Docker en WSL: (1) auth SSH
  con el ssh-agent multi-key del VPS rompía el clone de LibraGenda
  dentro del build (GitHub autentica con la primera key que acepte, sin
  reintentar) — `Dockerfile` ahora usa un alias de `Host` SSH dedicado
  por dependencia con `IdentitiesOnly`; (2) `app/asgi.py` no entendía
  el contrato de env vars que genera `libracore.provisioning`
  (`DATA_DIR`/`ADMIN_USER` en vez de `DATABASE_URL`/`GESTIOLIBRA_*`) —
  ahora deriva uno del otro cuando corresponde. Deploy key dedicada de
  solo lectura para el propio repo Gestiolibra (`id_ed25519_gestiolibra`).
- **Onboarding multi-negocio**: sistema de planes con enforcement real
  (`plans.py`: Básico/Estándar/Premium, $15k/$25k/$40k), tabla `modulos`
  (migración `0005_modulos`), `require_module()` gatea recordatorios/
  señas/facturación/dashboard con 403 (turnos y catálogo nunca se
  gatean; completar un turno nunca se bloquea, solo se salta la
  facturación si el plan no la incluye). Primera infraestructura de
  deploy de Gestiolibra: `Dockerfile`, `docker-compose.yml`, `app/asgi.py`,
  `scripts/{nuevo_cliente,panel_admin,npm_api,npm_setup}.py` (wrappers
  sobre `libracore.provisioning`, mismo patrón que Contalibra/Restolibra).
  Ver `DECISIONS.md` ADR-013.
- **Dashboard**: `GET /dashboard?date_from=&date_to=` (admin-only) —
  turnos (total y por estado en el rango, turnos de hoy), clientes
  (total activos, altas nuevas en el rango vía `client_billing.
  created_at` nuevo, migración `0004_client_created_at`) y
  recordatorios enviados/señas pendientes. Facturación/caja queda para
  una entrega futura (mismo alcance que MedLibra). `libragenda` a
  `v0.9.0` (agrega `list_sent()`/`list_by_status()`). Ver
  `DECISIONS.md` ADR-012.
- **Facturación/caja con LibraCore**: `client_billing` extiende `Client`
  con `cuit`/`condicion_iva` (migración `0003_client_billing`, primera
  extensión propia de Client), `PUT`/`GET /config/arca` (config ARCA de
  instancia única, admin-only), `POST /appointments/{id}/complete` — una
  factura por turno completado cuando el servicio tiene precio
  configurado (tipo A/B según condición de IVA), seña ya cobrada y saldo
  restante como movimientos de caja separados sobre la misma factura.
  `libragenda` a `v0.8.0`, `libracore` a `v0.16.1`. Mismo diseño exacto
  que MedLibra. Ver `DECISIONS.md` ADR-011.
- **SQLite pasa a ser el destino de producción por defecto** (arquitectura
  silo, mismo estándar que toda la familia Libra) — Postgres sigue
  soportado, ver `DECISIONS.md` ADR-010. LibraGenda actualizado a
  `v0.6.0` (activa `PRAGMA foreign_keys=ON` en toda conexión SQLite). CI
  ya no levanta un servicio Postgres, corre contra un archivo SQLite.
  Bug real corregido de paso: `BranchRepository.delete()` borraba el
  `Branch` antes que `BranchContactRow` (FK invertida) — invisible en
  SQLite sin FKs forzadas, ahora corregido. `DELETE` de sucursales,
  recursos, servicios y clientes ahora devuelve 409 (antes 500) cuando
  todavía tienen registros dependientes.
- Recordatorios y señas: `POST /reminders/dispatch` (admin-only, dispara
  avisos vencidos — 24h y 2h antes, fijo) y `POST`/`GET /appointments/{id}/deposit`
  + `POST /deposits/{id}/mark-paid`/`mark-failed`/`refund` (admin-only para
  confirmar). Notificaciones y pago sin proveedor real todavía: puertos
  placeholder (`LoggingNotificationPort`, `ManualPaymentPort`) que loguean
  en vez de enviar/cobrar — decisión acordada con el usuario, ver ADR-009.
  Sin migración nueva (`deposits`/`sent_reminders` son tablas de LibraGenda).
- Configuración comercial del negocio: `/branches/{id}/hours` (horario
  comercial semanal por sucursal, opt-in — sin configurar no gatea nada),
  `/services/{id}/prices` (precio por servicio y sucursal), `/branches`
  ahora acepta `phone`/`address`, `/business` (nombre comercial y moneda,
  singleton). `AppointmentService.create()`/`reschedule()` validan el
  horario comercial cuando está configurado. Migración
  `0002_business_config`.
- CI (GitHub Actions): `pytest` + smoke check de las dos cadenas de Alembic
  (LibraGenda + propia) contra Postgres de servicio, en cada push/PR a
  `main`. Requiere el secret `LIBRA_PAT` (ver `README.md`).
- Alembic propio (`migrations/`) para la tabla `users` — antes solo se
  creaba vía `create_all()`, sin efecto en un deploy real. Cadena de
  versión independiente (`alembic_version_gestiolibra`) para no colisionar
  con la de LibraGenda sobre la misma base.
- Login y roles básicos: `POST /auth/login`, `/auth/logout`, `GET /auth/me`,
  CRUD de usuarios admin-only en `/users`. Reusa `libracore.auth.SessionAuth`
  (cookie firmada); tabla `users` propia. Dos roles: `admin` (todo) y
  `staff` (solo su agenda de turnos). Todos los routers existentes quedan
  gateados por rol. Completa la Fase 1 (MVP operativo). Suma `libracore`
  como dependencia nueva.
- `POST /appointments/{id}/cancel` y `POST /appointments/{id}/reschedule`,
  ambos con `reason` opcional en el body (usa el campo agregado en
  LibraGenda `v0.5.0`).
- LibraGenda actualizado a `v0.5.0` (motivo opcional en cancelación/
  reprogramación de turnos). Base `gestiolibra` migrada a `0007_appointment_reason`.
- Normalización documental al estándar híbrido por producto.

## 2026-07-18 — Disponibilidad y agenda

- CRUD de ventanas semanales, bloqueos y excepciones por recurso.
- Agenda por rango de fechas.
- Validación de turnos contra disponibilidad real configurada.
- Corrección upstream en LibraGenda para datetimes UTC-aware entre SQLite y PostgreSQL.

## 2026-07-18 — CRUD del MVP

- CRUD de sucursales, recursos, servicios y clientes.
- Repositorio compartido LibraGenda extendido con operaciones get/update/delete.

## 2026-07-18 — Integración inicial

- Separación de routers y servicios de aplicación.
- LibraGenda `v0.3.0` pineado.
- PostgreSQL dedicado migrado y verificado end-to-end en entorno dev real.
- Smoke test HTTP inicial.

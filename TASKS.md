# Tasks — Gestiolibra

Trabajo concreto vigente. La dirección estratégica permanece en `ROADMAP.md`; este archivo no es un historial.

## En curso

Rediseño visual del frontend con Tailwind CSS + shadcn/ui (ver
ADR-025): construido y verificado manualmente en local. Falta
desplegarlo a `dev.gestiolibra.com.ar` (rebuild de imagen + confirmar
en el dominio público).

## Próximas

- [ ] `gestiolibra.com.ar` (dominio pelado, sin subdominio) no tiene
      proxy host en NPM ni certificado — HTTPS falla el handshake
      directamente, HTTP cae en el fallback default de NPM. Solo
      `dev.gestiolibra.com.ar`/`prueba.gestiolibra.com.ar` están
      armados hoy. Decisión explícita del usuario (2026-07-23): dejarlo
      así hasta que haya una instancia de producción real o un sitio de
      marketing propio (mismo patrón que `contalibra.com.ar`/
      `restolibra.com.ar` → contenedor `-web`) — no es un bug, no
      apurar un proxy provisorio. Para entrar hoy, usar
      `https://dev.gestiolibra.com.ar`.
- [ ] Extender el frontend con facturación (config ARCA, ver factura
      por turno completado) — clientes y dashboard ya se sumaron
      (ver ADR-021).
- [ ] El input de horario del formulario de turno (`datetime-local`)
      manda la hora tal cual la eligió el usuario en su navegador, y el
      backend la trata como UTC directo (`_as_utc()`, sin conversión de
      timezone de sucursal — limitación preexistente, no introducida
      por el frontend). Con un frontend real esto se vuelve visible para
      un usuario de verdad, no solo para tests: un negocio fuera de UTC
      va a ver/cargar turnos con la hora corrida. Resolverlo requiere
      timezone de sucursal de punta a punta (LibraGenda ya expone
      `Branch.timezone`, no está conectado al frontend todavía).
- [ ] `libracore.provisioning.panel_admin.cmd_actualizar` tiene
      hardcodeado un solo `--ssh default=<archivo>` — funciona para
      Gestiolibra apuntando `LIBRACORE_SSH_KEY` al socket del ssh-agent
      persistente del VPS (`agent-multi-libra.sock`, con las claves de
      libracore y libragenda cargadas), pero valdría la pena que LibraCore
      soporte esto de forma más explícita si aparece un tercer producto
      con la misma necesidad (ver ADR-013).
- [ ] `libracore.provisioning.nuevo_cliente._esperar_db_lista()` puede
      agotar su timeout antes de que el contenedor recién creado termine
      de crear la tabla `modulos` (nos pasó con el primer alta real,
      aunque por una causa puntual — el contenedor crasheaba por el bug
      de `asgi.py` ya resuelto, no por lentitud real) — cuando eso pasa,
      el plan elegido no se aplica solo, hay que correr
      `plans.aplicar_plan_en_db(db_path, plan)` a mano una vez sí levantó.
      El mensaje `[WARN]` que emite ya avisa de esto. No es un bug de
      Gestiolibra, es una condición de carrera genérica de
      `libracore.provisioning` — evaluar si vale la pena que esa función
      espere más o reintente, si aparece de nuevo con un tercer producto.
- [ ] Upload real de certificado/clave ARCA (`PUT /config/arca` hoy acepta
      solo paths en el filesystem del servidor — ver ADR-011).
- [ ] Revisar el cálculo de IVA de facturación (21% fijo) con un contador
      antes de facturar contra ARCA real (ver ADR-011).
- [ ] Cargar credenciales ARCA reales cuando el usuario las tenga — hoy
      solo funciona en modo mock (`ENV=development`).

## Bloqueadas

Ninguna bloqueada registrada.

Resuelto (2026-07-21): Alembic propio de Gestiolibra para la tabla `users`
(`alembic_version_gestiolibra`, cadena independiente de la de LibraGenda
sobre la misma base) — ver `README.md`.

Resuelto (2026-07-22): configuración comercial del negocio — horario por
sucursal, precio por servicio y sucursal, contacto de sucursal y datos
globales del negocio. Migración `0002_business_config`.

Resuelto (2026-07-22): recordatorios y señas — `POST /reminders/dispatch`,
`POST`/`GET /appointments/{id}/deposit`, `POST /deposits/{id}/mark-paid`/
`mark-failed`/`refund`. Notificaciones y pago con puertos placeholder
(`LoggingNotificationPort`, `ManualPaymentPort`) hasta definir proveedor
real. Sin migración nueva (tablas de LibraGenda ya migradas).

Resuelto (2026-07-22): SQLite como destino de producción por defecto
(estándar de familia, ver `DECISIONS.md` ADR-010). LibraGenda a `v0.6.0`.
Bug real corregido: `BranchRepository.delete()` con orden de borrado
invertido (FK), invisible sin FKs forzadas. `DELETE` de sucursales/
recursos/servicios/clientes ahora devuelve 409 en vez de 500 con
dependientes. CI simplificado (sin servicio Postgres).

Resuelto (2026-07-22): facturación/caja con LibraCore (ver ADR-011).
`client_billing` extiende `Client` con `cuit`/`condicion_iva` (migración
`0003_client_billing`, primera extensión propia de Client — antes se
usaba el genérico de LibraGenda sin extensión). `POST /appointments/
{id}/complete` factura el turno (LibraGenda `v0.7.0`) cuando el servicio
tiene precio configurado — una sola factura con `libracore.
arca_facturacion` (LibraCore `v0.16.1`), tipo A/B según condición de
IVA, seña ya cobrada y saldo restante como movimientos de caja
separados apuntando a la misma factura. `PUT`/`GET /config/arca`
(admin-only, instancia única). `libragenda` a `v0.8.0` (`medio_pago`
opcional en depósitos). Mismo diseño exacto que MedLibra, portado casi
verbatim — ver `DECISIONS.md` de ese repo (ADR-016) para el detalle
completo. 30 tests nuevos, verificado además end-to-end contra
archivos SQLite reales.

Resuelto (2026-07-22): dashboard — turnos (total y por estado en un
rango, turnos de hoy), clientes (total activos, altas nuevas en el
rango) y recordatorios enviados/señas pendientes (ver ADR-012).
Facturación/caja quedó fuera de este primer corte a pedido del usuario,
mismo alcance que MedLibra. `GET /dashboard?date_from=&date_to=`
(admin-only). `client_billing.created_at` (migración
`0004_client_created_at`, nullable, sin backfill). `libragenda` a
`v0.9.0` (`list_sent()`/`list_by_status()`). 7 tests nuevos (113 en
total), verificado además end-to-end contra archivos SQLite reales.

Resuelto (2026-07-22): sistema de planes con enforcement real (ver
ADR-013). `plans.py` (Básico/Estándar/Premium, $15k/$25k/$40k), tabla
`modulos` (migración `0005_modulos`, seed por defecto: todo habilitado
hasta aplicar un plan). `require_module()` gatea recordatorios/señas/
facturación/dashboard con 403 — turnos y catálogo nunca se gatean;
`complete()` de turno nunca se bloquea por plan, solo salta la
facturación si no corresponde. Dockerfile + docker-compose.yml +
scripts/{nuevo_cliente,panel_admin,npm_api,npm_setup}.py (wrappers sobre
`libracore.provisioning`) — primera infraestructura de deploy de
Gestiolibra, nunca se había desplegado a ningún servidor. Deploy key
nueva de solo lectura para LibraGenda (`id_ed25519_libragenda`) +
ssh-agent persistente en el VPS con ambas claves. 17 tests nuevos (130
en total), verificado además end-to-end contra un archivo SQLite real
aplicando planes en vivo.

Resuelto (2026-07-23): branding y dominio por cliente, incluido el
flujo automático de alta contra un cliente real (ver ADR-016/ADR-017).
"Branding" más allá de dominio+SSL no aplica sin frontend.
`dev.gestiolibra.com.ar` con proxy NPM + certificado Let's Encrypt real,
reutilizando la misma instancia de NPM y credenciales que ya usan
Contalibra/Restolibra (sin generar nada nuevo). Ningún cambio de código
en el repo — la maquinaria (`scripts/npm_api.py`/`npm_setup.py`) ya
existía desde el onboarding multi-negocio. Hallazgo inicial: copiar la
config de Contalibra trajo un `forward_host` (nombre de contenedor
ajeno) que no aplicaba a Gestiolibra; corregido a la gateway real de la
red docker compartida (`stack_stack-net`, `172.18.0.1`). **Con ese
valor corregido, se probó el flujo automático real**
(`libracore.provisioning.nuevo_cliente._setup_npm_proxy()`, la misma
función que usaría un alta real) contra el cliente `prueba` —
`prueba.gestiolibra.com.ar` quedó armado con proxy + SSL sin ningún
código nuevo ni workaround manual, confirmando que no era un bug de
`libracore.provisioning` sino un valor de configuración copiado mal.
Ambos dominios verificados con `curl` (200, certificado válido).

Resuelto (2026-07-23): backups verificados (cierra ese ítem de Fase 3,
ver ADR-017). `panel_admin.py backup`/`restore-db` (wrappers sobre
`libracore.provisioning.panel_admin.cmd_backup`/`cmd_restore_db`, ya
existían, sin código nuevo) probados de punta a punta contra el cliente
`prueba`: fila marcadora insertada → backup (tar.gz completo + copia
WAL-safe de la DB vía `sqlite3.Connection.backup()`) → datos mutados a
propósito → restore desde el backup → confirmado que la fila marcadora
vuelve y la mutación posterior desaparece, contenedor sano tras el
reinicio. Sin cambios de código.

Resuelto (2026-07-23): id de cliente autogenerado si se omite (ver
ADR-024). `POST /clients` acepta `id` opcional (`uuid4()` si no se
manda) — sacado el campo del formulario de alta del frontend, fricción
real para una operación que pasa todo el tiempo (a diferencia del
catálogo, armado una sola vez por un admin). 1 test nuevo (136 en
total), verificado además en el browser contra la API real.

Resuelto (2026-07-23): la ruta `/dashboard` del frontend colisionaba
con el endpoint real `GET /dashboard` de la API (mismo origen, mismo
espacio de rutas, sin prefijo `/api` — ver ADR-023). Navegación directa
(F5, URL escrita a mano) a esa página devolvía el JSON de error de la
API en vez de la SPA; con el nav (ruteo del lado del cliente) nunca se
notaba. Renombrada la ruta del frontend a `/reportes` — el endpoint de
la API sigue igual. Riesgo documentado para páginas futuras: evitar
nombres de ruta que coincidan con paths de nivel superior existentes
en la API.

Resuelto (2026-07-23): el frontend quedaba congelado en el primer
build (ver ADR-022). El usuario reportó que `dev.gestiolibra.com.ar`
no mostraba las páginas de Clientes/Dashboard recién agregadas pese a
un rebuild+recreate aparentemente exitoso — el volumen anónimo de
ADR-020 solo se siembra desde la imagen la primera vez que se crea, un
rebuild posterior no lo actualiza. `Dockerfile` ahora hornea el build
en `/opt/frontend-dist` (fuera de `/app`, que el compose de dev
bind-montea entero); `app/asgi.py` lo busca ahí primero, cae al
`frontend/dist` del repo si no existe (build local sin Docker).
Verificado con rebuild `--no-cache` + recreate real: el bundle servido
coincide con el hash del build recién generado. De paso se encontró y
corrigió que el usuario admin del contenedor de dev había quedado con
una contraseña vieja (bootstrap solo corre una vez, no se actualiza
en rebuilds) — reseteado para coincidir con `.env` actual.

Resuelto (2026-07-23): frontend extendido con Clientes y Dashboard
(ver ADR-021). Clientes: lista para staff+admin, alta/edición/baja
solo admin (refleja el gating que ya existía en la API, ADR-018).
Dashboard: mismo resumen que `GET /dashboard`, oculto del nav para
staff, 403 mostrado como mensaje explicativo. `Layout.tsx` nuevo
(header+nav compartido, antes solo en Agenda). Verificado manualmente
en el browser con ambos roles (CRUD completo de clientes probado
contra la API real, dashboard con datos reales del rango
seleccionado), sin errores de consola. Sin cambios de backend.
Desplegado a `dev.gestiolibra.com.ar` (rebuild de imagen + recreate del
contenedor), verificado con `curl` y en el browser real sin errores de
consola.

Resuelto (2026-07-23): frontend MVP desplegado y verificado en
`dev.gestiolibra.com.ar` real (ver ADR-019/ADR-020). Primer build de
Docker con el stage de node (`frontend-build`) en el VPS — terminó sin
errores, pero el contenedor servía 404 en cualquier ruta no-API: el
bind mount `./:/app` del `docker-compose.yml` de dev tapaba el
`frontend/dist` horneado en la imagen con el directorio vacío del host
(artefacto de build, gitignoreado, no existe fuera del stage de node).
Corregido con un volumen anónimo para ese subpath específico. Verificado
con `curl` (root sirve `index.html`, `/assets/*.js` 200, `/health` 200,
ruta de cliente inexistente cae al fallback de la SPA) y en el browser
real contra `dev.gestiolibra.com.ar` (login carga, error de credenciales
inválidas se muestra correctamente, sin errores de consola).

Resuelto (2026-07-23): lectura de catálogo abierta a staff (ver
ADR-018). `branches`/`resources`/`services`/`clients` — `GET` pasa a
staff+admin, `POST`/`PUT`/`DELETE` siguen admin-only. Encontrado al
construir el frontend: sin esto, un usuario staff no podía ni siquiera
listar recursos/servicios/clientes para armar un turno. 4 tests nuevos
(135 en total).

Resuelto (2026-07-23): dashboard suma facturación/caja (ver ADR-015).
`GET /dashboard` incluye `facturacion.facturas_emitidas_en_periodo` y
`facturacion.caja` (ingresos/egresos/saldo del período + saldo total),
reutilizando `get_caja_resumen()`/`get_facturas_filtradas()` de
`libracore.db`, ya genéricos — sin gating extra por módulo, porque en
el diseño de planes actual "facturacion" y "dashboard" solo existen
juntos. 1 test nuevo (131 en total), verificado además end-to-end
contra un archivo SQLite real (turno completado con precio configurado
→ factura → dashboard del día refleja la factura y el ingreso de caja).

Resuelto (2026-07-22): deploy real a producción en el VPS + alta del
primer cliente de prueba (cierra el onboarding multi-negocio de
ADR-013). Dos bugs reales encontrados y corregidos recién en el primer
build/alta real (invisibles en el desarrollo local):
1. GitHub autentica toda la conexión SSH con la primera key del agente
   que acepte y no reintenta con otra si esa key no tiene acceso al
   repo pedido — con el ssh-agent multi-key del VPS eso rompía el clone
   de LibraGenda dentro del build (`Repository not found` pese a tener
   su propia deploy key cargada). Arreglado en el `Dockerfile`: cada
   dependencia usa su propio alias de `Host` SSH con `IdentitiesOnly` +
   su public key específica (no son secreto, se hornean en la imagen),
   forzando qué identidad del agente se ofrece por alias.
2. `app/asgi.py` esperaba `DATABASE_URL`/`GESTIOLIBRA_*` (las env vars
   del `docker-compose.yml` de dev de este repo) pero
   `libracore.provisioning` genera un `docker-compose.yml` por cliente
   con el contrato genérico que Contalibra/Restolibra ya leen
   directamente (`DATA_DIR`/`ADMIN_USER`/`ADMIN_PASSWORD`/
   `ADMIN_NOMBRE`) — el contenedor del primer cliente crasheaba con
   `KeyError: DATABASE_URL`. `asgi.py` ahora deriva `DATABASE_URL` y
   `GESTIOLIBRA_LIBRACORE_DB_PATH` de `DATA_DIR` cuando está presente,
   sin tocar `libracore.provisioning`.

El propio repo Gestiolibra se clonó al VPS con una deploy key nueva y
dedicada (`id_ed25519_gestiolibra`, solo lectura) — separada de las dos
keys que ya autentican las dependencias LibraGenda/LibraCore durante el
build. Cliente de prueba (`prueba`, puerto 8076, plan Premium)
levantado y verificado: build de imagen real, contenedor healthy,
tablas creadas, plan aplicado (a mano, ver el punto de
`_esperar_db_lista()` en "Próximas"), login admin funcionando. Queda
corriendo en el VPS como evidencia del pipeline completo.

## Notas de testing

- La suite (`pytest`) usa cookies de sesión firmadas con timestamp
  (`itsdangerous`, vía `libracore.auth.SessionAuth`). En este entorno WSL2
  se confirmó empíricamente que el reloj del sistema puede saltar hacia
  atrás ~20s en medio de una corrida (desincronización de reloj WSL2↔host
  Windows) — eso invalida un cookie válido con `SignatureExpired: age <0`,
  causando un 401 intermitente y no reproducible (~1 cada 10-15 corridas
  completas). No es un bug de la app: no ocurre en el servidor real de
  producción (reloj no virtualizado). Si un test de auth falla una sola vez
  de forma aislada sin cambios de código, reintentar antes de investigar.

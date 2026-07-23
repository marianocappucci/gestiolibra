# Tasks — Gestiolibra

Trabajo concreto vigente. La dirección estratégica permanece en `ROADMAP.md`; este archivo no es un historial.

## En curso

Ninguna en curso — onboarding multi-negocio (ver ADR-013) cerrado, ver
"Resuelto" más abajo.

## Próximas

- [ ] Dashboard: sumar facturación/caja (dejado fuera del primer corte
      a pedido explícito del usuario) — reutilizando
      `libracore.db.caja.get_caja_resumen()`, ya genérico.
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
- [ ] Branding y dominio por cliente.
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

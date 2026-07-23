# Decisiones arquitectónicas — Gestiolibra

Registro ADR. Las decisiones no se borran; si dejan de aplicar, se marcan como reemplazadas.

## ADR-001 — Usar LibraGenda como motor de agenda

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: Gestiolibra necesita turnos, disponibilidad, recursos y servicios sin incorporar lógica clínica.
- Decisión: consumir LibraGenda como dependencia versionada y mantener en Gestiolibra solo el flujo HTTP y las reglas del vertical.
- Consecuencias: reutilización entre verticales y menor duplicación; los cambios genéricos deben corregirse upstream.

## ADR-002 — Corregir problemas del motor en LibraGenda, no con workarounds locales

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: se detectaron diferencias reales entre SQLite y PostgreSQL y faltantes CRUD en el repositorio compartido.
- Decisión: corregir el comportamiento común en LibraGenda, versionarlo con tag y actualizar el pin del consumidor.
- Consecuencias: un único contrato para consumidores, con promoción y verificación separadas.

## ADR-003 — Ejecutar migraciones de LibraGenda desde el repo upstream

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: las migraciones no forman parte del wheel de LibraGenda.
- Decisión: el deploy clona LibraGenda en el tag pineado y ejecuta Alembic antes de levantar Gestiolibra.
- Consecuencias: las migraciones tienen una sola fuente de verdad y el deploy es reproducible.

## ADR-004 — Mantener el producto fuera de dominios no clínicos

- Estado: aceptada
- Fecha: 2026-07-18
- Contexto: la familia Libra tiene verticales de salud y gastronomía independientes.
- Decisión: excluir de Gestiolibra historia clínica, recetas, estudios y funcionalidades gastronómicas.
- Consecuencias: el producto conserva un alcance claro para negocios de servicios generales.

## ADR-005 — Reusar SessionAuth de LibraCore, tabla de usuarios propia

- Estado: aceptada
- Fecha: 2026-07-21
- Contexto: Gestiolibra necesita login y roles (`admin`/`staff`). LibraCore
  ya tiene `SessionAuth` (cookie firmada, roles, probado en producción por
  Contalibra/Restolibra), diseñado explícitamente para reusarse entre
  productos (recibe callbacks en vez de asumir un schema). Su tabla de
  usuarios (`libracore.db.usuarios`) no sirve tal cual: está acoplada a
  SQLite vía `libracore.db.core.get_connection` con SQL crudo, y Gestiolibra
  usa PostgreSQL/SQLAlchemy.
- Decisión: sumar `libracore` como dependencia solo por `SessionAuth` (la
  mecánica de cookie/sesión, agnóstica de storage). Tabla `users` propia en
  SQLAlchemy/PostgreSQL con el mismo algoritmo de hashing (PBKDF2, 260k
  iteraciones) que `libracore.db.usuarios`, reimplementado en
  `app/security.py` en vez de importar las funciones privadas
  (prefijo `_`) de ese módulo.
- Consecuencias: Gestiolibra no reinventa la mecánica de sesión/cookie (ya
  auditada), pero sí duplica ~20 líneas de hashing puro sin dependencias —
  trade-off aceptado sobre acoplarse a un módulo interno de otro paquete no
  pensado para reuso directo. `SessionAuth.require_auth`/`require_role`
  (con redirect 307 a `/login`) tampoco se reusan: Gestiolibra es una API
  JSON pura sin esa página, así que `app/auth.py` define sus propias
  dependencias con 401/403.

## ADR-006 — Dos roles para el MVP: admin y staff

- Estado: aceptada
- Fecha: 2026-07-21
- Contexto: el negocio necesita diferenciar quién administra el negocio
  (sucursales, recursos, servicios, clientes, usuarios) de quién solo
  atiende turnos (empleados).
- Decisión: `admin` con acceso completo; `staff` limitado a `/appointments`
  y `/resources/{id}/agenda` — no puede tocar catálogo ni gestionar otros
  usuarios. Gating aplicado centralizado por router en `app/main.py`, no
  repetido endpoint por endpoint.
- Consecuencias: esquema simple y suficiente para el MVP; agregar roles más
  finos (ej. gerente de sucursal) queda para cuando aparezca una necesidad
  real, no se anticipa.

## ADR-007 — Alembic propio de Gestiolibra, cadena independiente de la de LibraGenda

- Estado: aceptada
- Fecha: 2026-07-21
- Contexto: la tabla `users` (y cualquier tabla futura que no pertenezca a
  LibraGenda) solo se creaba vía `Base.metadata.create_all()` en
  `create_app()` — sin efecto real en un deploy de producción, que no llama
  a `create_all()` sino que corre las migraciones de LibraGenda (ver
  ADR-003). Sin una migración propia, `users` nunca se hubiera creado fuera
  de dev/tests.
- Decisión: `migrations/` propio en este repo (mismo layout que LibraGenda:
  `alembic.ini`, `env.py`, `versions/`), pero con dos diferencias
  deliberadas: (1) `target_metadata = None` en vez de `Base.metadata` —
  `UserRow` comparte el `Base` declarativo de LibraGenda, así que apuntar
  el autogenerate ahí vería también las tablas del motor como propias de
  esta cadena; las migraciones se escriben a mano, igual que ya hace
  LibraGenda. (2) `version_table = "alembic_version_gestiolibra"` — ambas
  cadenas corren contra la misma base física; con el nombre default
  colisionarían.
- Consecuencias: el deploy real de Gestiolibra corre dos pasos de Alembic
  en vez de uno (LibraGenda primero, Gestiolibra después) — verificado
  contra PostgreSQL real que las dos cadenas de versión conviven sin
  pisarse. Cualquier tabla nueva propia de Gestiolibra (no de LibraGenda)
  se agrega acá, nunca en el repo de LibraGenda.

## ADR-008 — Configuración comercial: opt-in, y separada de LibraGenda

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: "configuración comercial" estaba anotada en `TASKS.md` desde
  el scaffold sin nunca detallarse. Preguntado al usuario, se acordó
  alcance concreto: horario comercial por sucursal, precio por servicio y
  sucursal, y datos de contacto/marca del negocio.
- Decisión: las tres piezas quedan como tablas propias de Gestiolibra
  (`branch_hours`, `service_prices`, `branch_contacts`,
  `business_settings`), no en LibraGenda — el motor no calcula precios
  (mismo principio que señas/`Deposit`) ni tiene noción de "horario del
  negocio" a nivel sucursal (solo disponibilidad por recurso), y ningún
  otro vertical de la familia pidió esto todavía como para justificar
  subirlo al motor compartido (ver ADR-002: los cambios genéricos se
  corrigen en LibraGenda, pero esto no es un cambio genérico probado por
  dos consumidores, es específico de este negocio por ahora). El horario
  comercial es **opt-in**: una sucursal sin horario configurado no gatea
  nada — se decidió así para no romper ningún flujo de turnos existente
  con una restricción nueva no pedida; solo al configurarlo se exige
  además de la disponibilidad del recurso (intersección).
- Consecuencias: si MedLibra (o un futuro vertical) pide horario comercial
  por sucursal, evaluar en ese momento si conviene subirlo a LibraGenda
  (misma señal que ya disparó la extracción de CRUD de catálogo y el fix
  de datetimes). Precio y contacto/marca son negocio/vertical-specific casi
  con certeza — poco probable que se generalicen.

## ADR-009 — Recordatorios y señas: puertos placeholder hasta elegir proveedor

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: LibraGenda ya resuelve el dominio de recordatorios
  (`ReminderDispatcher`, `due_reminders()`) y señas (`DepositManager`) vía
  dos puertos (`NotificationPort`, `PaymentPort`) que Gestiolibra debe
  implementar. No hay todavía un proveedor de notificaciones (email/SMS/
  WhatsApp) ni de pagos (MercadoPago u otro) elegido para el negocio.
  Preguntado al usuario cómo resolver ambos vacíos antes de codificar.
- Decisión: implementar ambos puertos como placeholders explícitos en vez
  de bloquear la feature o improvisar una integración real a medias.
  `LoggingNotificationPort` loguea cada recordatorio vencido en vez de
  enviarlo. `ManualPaymentPort` no cobra ni reintegra solo — `request_charge`/
  `request_refund` solo loguean la intención; la confirmación real de la
  seña (efectivo, transferencia, link de MercadoPago enviado a mano) la
  hace un admin a mano vía `POST /deposits/{id}/mark-paid`/`mark-failed`/
  `refund`. Los dos endpoints de disparo (`/reminders/dispatch`) y consulta/
  confirmación de señas quedan operativos igual, con el reemplazo del canal
  como el único trabajo pendiente cuando se elija proveedor.
- Consecuencias: la feature es usable en producción sin esperar una
  integración externa (recordatorios visibles en logs para seguimiento
  manual, señas cobradas y confirmadas por el propio negocio). El costo es
  operativo, no técnico: alguien tiene que mirar los logs y marcar los pagos
  a mano hasta que se reemplacen los puertos. `NotificationPort`/
  `PaymentPort` son `Protocol` sin `@runtime_checkable`, así que la
  conformidad es estructural (duck typing), no verificada por `isinstance`.

## ADR-010 — SQLite como destino de producción por defecto

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: al scopear si MedLibra debía componer LibraCore para
  facturación, salió a la luz que Contalibra/Restolibra despliegan con
  arquitectura silo real (instancia + base SQLite aislada por cliente) y
  que Gestiolibra ya prevé exactamente el mismo patrón de despliegue
  (Docker, `panel_admin.py`, sin infraestructura de producción propia
  todavía — ver "Infraestructura" en la entidad de este repo en la wiki).
  Mantener Gestiolibra en PostgreSQL mientras el resto de la familia usa
  SQLite no aportaba nada real y complicaba cualquier composición futura
  con LibraCore (SQLite-only, sin capa de abstracción). Decisión del
  usuario, registrada como estándar de familia en LibraGenda (ver
  `DECISIONS.md` de ese repo, ADR-005) y en `estandares-desarrollo.md`
  del wiki.
- Decisión: `DATABASE_URL` pasa a apuntar a un archivo SQLite por
  defecto en vez de una base Postgres. Sin cambios de código propios:
  `LibraGenda.configure(url)` ya activa `PRAGMA foreign_keys=ON`
  automáticamente para cualquier conexión SQLite (ver ADR-005 de
  LibraGenda) — antes esto solo se probaba contra SQLite en memoria
  (tests) o contra Postgres real, nunca contra un archivo SQLite con FKs
  forzadas. Al verificar contra un archivo real con FKs activas, salió
  a la luz un bug preexistente (no introducido por este cambio, ya
  estaba ahí desde que se creó `BranchRepository`): `delete()` borraba
  el `Branch` genérico de LibraGenda **antes** que `BranchContactRow`
  (extensión propia con FK a `branches.id`) — mismo patrón de bug que
  `PatientRepository.delete()` de MedLibra (ver `DECISIONS.md` de ese
  repo, ADR-011). Postgres ya lo hubiera bloqueado siempre (fuerza FKs
  por default); nunca se ejerció ese camino contra Postgres real en las
  verificaciones anteriores. Corregido invirtiendo el orden. De paso se
  encontró que `DELETE /branches/{id}`, `/resources/{id}`,
  `/services/{id}` y `/clients/{id}` no traducían `IntegrityError` a un
  409 limpio (solo capturaban `KeyError`) — cualquier intento de borrar
  una entidad de catálogo con dependientes devolvía un 500 crudo en vez
  de un error entendible. Agregado el `except IntegrityError` faltante
  en los cuatro routers.
- Consecuencias: CI simplificado (sin servicio Postgres, smoke check
  contra un archivo SQLite plano). Verificado con la suite completa y
  end-to-end contra un archivo SQLite real (creación, turno, recordatorio,
  seña, y los tres casos de borrado bloqueado por FK — sucursal con
  recurso, recurso con turno — ahora devolviendo 409 en vez de 500).
  Postgres sigue funcionando si se pasa esa `DATABASE_URL`; no se retira
  como opción.

## ADR-011 — Facturación/caja con LibraCore: mismo diseño que MedLibra

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: pregunta abierta en `TASKS.md` desde que Gestiolibra sumó
  LibraCore como dependencia (solo para `SessionAuth`): ¿también compone
  el motor de facturación/caja? MedLibra ya había resuelto esta misma
  pregunta el mismo día, con `libracore.arca_facturacion` construido,
  probado y en producción real (Contalibra/Restolibra migrados al shim
  nuevo). El usuario confirmó (`AskUserQuestion`) incorporar el mismo
  diseño en Gestiolibra — mucho menos riesgo que la ronda de MedLibra
  porque no hay nada nuevo que descubrir en LibraCore, solo componerlo.
- Decisión — dominio: a diferencia de MedLibra (que ya tenía `Patient`
  como extensión de `Client`), Gestiolibra usaba el `Client` genérico de
  LibraGenda **sin ninguna extensión propia** — se agregó
  `client_billing` (`cuit`/`condicion_iva`, migración `0003_client_
  billing`), mismo patrón exacto que `patients` de MedLibra: una tabla
  de extensión con FK a `clients.id`, coordinada en el borde de la API
  vía `ClientRepository` (antes el router `clients.py` hablaba directo
  con `SqlAlchemyCatalogRepository`, ahora pasa por esta capa nueva).
  `client_billing.delete()` borra la extensión antes que el `Client`
  genérico — mismo orden ya corregido en `BranchRepository`/
  `PatientRepository` de esta familia, para no repetir ese bug.
- Decisión — arquitectura y flujo de facturación: **idénticos a
  MedLibra** (ver `DECISIONS.md` de ese repo, ADR-016, para el detalle
  completo — no se repite acá porque no hay ninguna decisión de negocio
  distinta). `app/services/billing.py` portado casi verbatim (única
  diferencia: `EMPRESA = "negocio"` en vez de `"consultorio"`, y
  `client` en vez de `patient` en los nombres). `POST /appointments/
  {id}/complete` factura el turno completo cuando el servicio tiene
  precio configurado, una sola factura (tipo A/B según condición de
  IVA del cliente), seña y saldo como movimientos de caja separados.
- Consecuencias: `libragenda` bumpeado a `v0.8.0`, `libracore` a
  `v0.16.1` (mismo pin que MedLibra). 30 tests nuevos (106 en total).
  Verificado con la suite completa (con reruns para descartar el flake
  ya documentado del reloj de WSL2) + end-to-end contra archivos SQLite
  reales (no memoria — `libracore.db` abre una conexión nueva por
  llamada): login, config ARCA, turno con seña parcial + saldo, factura
  tipo B con CAE simulado, dos movimientos de caja sobre la misma
  factura. Migración `0003` verificada con el ciclo completo
  `upgrade`→`downgrade`→`upgrade` contra un archivo real (con la cadena
  de LibraGenda aplicada primero). Mismas simplificaciones documentadas
  que MedLibra, no bloqueantes: IVA fijo al 21%, certificado/clave ARCA
  como paths de texto en vez de upload multipart.

## ADR-012 — Dashboard: mismo diseño que MedLibra (turnos, clientes en vez de facturación/caja)

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: mismo alcance que MedLibra confirmó para su propio
  dashboard el mismo día — el usuario eligió replicarlo tal cual acá
  (`AskUserQuestion`): turnos, clientes y recordatorios/señas.
  **Facturación/caja queda afuera** de este primer corte (entrega
  futura, aunque `libracore.db.caja.get_caja_resumen()` ya existiría
  lista para reusar).
- Decisión: `GET /dashboard?date_from=&date_to=` (admin-only, fechas
  requeridas). Turnos (total en el rango, conteo por estado, turnos de
  **hoy** — fecha real del servidor, no del rango pedido), clientes
  (total activos, altas nuevas en el rango vía `client_billing.
  created_at` nuevo — migración `0004_client_created_at`, nullable, sin
  backfill) y recordatorios enviados en el rango + señas pendientes sin
  acotar por fecha. `DashboardService` portado casi verbatim desde
  MedLibra (única diferencia real: "clientes" en vez de "pacientes" en
  los nombres — el resto de la lógica es idéntica, ninguna decisión de
  negocio distinta). Reutiliza `SentReminderRepository.list_sent()`/
  `DepositRepository.list_by_status()` de LibraGenda `v0.9.0` (ADR-008
  de ese repo), agregados el mismo día para esta misma necesidad en
  MedLibra.
- Consecuencias: `libragenda` bumpeado a `v0.9.0`. 7 tests nuevos (113
  en total). Verificado con la suite completa (con reruns para
  descartar el flake ya documentado del reloj de WSL2) + end-to-end
  contra archivos SQLite reales. Migración `0004` verificada con el
  ciclo `upgrade`→`downgrade`→`upgrade` contra un archivo real (con la
  cadena de LibraGenda aplicada primero). Mismo hallazgo de proceso que
  MedLibra tuvo en su propio test (no repetido acá porque el test se
  escribió ya con la corrección incorporada desde el principio):
  comparar un turno contra un rango de "hoy" calculado por separado
  falla cerca de medianoche UTC — el test deriva el rango de consulta
  de la fecha real del turno creado.

## ADR-013 — Onboarding multi-negocio: planes con enforcement real + infraestructura de deploy

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: "onboarding multi-negocio" venía anotado sin alcance en
  `TASKS.md`/`ROADMAP.md` desde el scaffold. Antes de codificar se
  resolvieron con el usuario (`AskUserQuestion`) tres decisiones reales:
  (1) qué significa "onboarding" acá — infraestructura de deploy para
  poder dar de alta el primer cliente real (no un wizard dentro de la
  app); (2) si hace falta un sistema de planes ahora — sí, con
  enforcement real (bloquear rutas según el plan), no solo una
  definición informativa; (3) estructura de planes — Básico (catálogo/
  turnos/clientes, siempre gratis) / Estándar (+ recordatorios/señas) /
  Premium (+ facturación/dashboard), $15k/$25k/$40k (Gestiolibra apunta
  a negocios más chicos que Contalibra, que arranca en $29k).
- Decisión — planes y gating: `plans.py` en la raíz del repo (mismo
  patrón exacto que Contalibra: `PLANES`, `PLAN_MODULOS`,
  `aplicar_plan_en_db()` con `sqlite3` crudo). Tabla `modulos` propia
  (migración `0005_modulos`) — a diferencia de Contalibra, que la crea
  vía `init_db()` inline sin Alembic, acá se creó como cualquier otra
  tabla de Gestiolibra. **Seed por defecto: todo habilitado**
  (`habilitado=True`) hasta que se aplique un plan real — mismo criterio
  que Contalibra, para no romper ningún flujo de dev/tests existente.
  `require_module(nombre)` (dependency factory, mismo patrón que
  `require_role`) gatea completo los routers de recordatorios/señas/
  facturación/dashboard con 403; **turnos y catálogo nunca se gatean**.
  El caso más delicado, `complete()` de turno, no se bloquea por plan —
  si "facturacion" no está habilitado, simplemente no factura (el turno
  igual se completa), nunca deja un turno atascado por una limitación
  comercial.
- Decisión — infraestructura de deploy: Gestiolibra no tenía Dockerfile
  ni docker-compose.yml — nunca se había desplegado a ningún servidor.
  Se construyó mirando el patrón ya probado de Contalibra/Restolibra
  (`Dockerfile`, `docker-compose.yml` con servicio `-dev`, wrappers
  `scripts/nuevo_cliente.py`/`panel_admin.py`/`npm_api.py`/
  `npm_setup.py` sobre `libracore.provisioning`, genérico y ya probado
  en producción real). **Hallazgo real en el camino**: Gestiolibra usa
  `git+https://` para instalar LibraGenda/LibraCore en `pyproject.toml`
  (así funciona el dev local en WSL, sin identidad SSH contra GitHub),
  a diferencia de Contalibra/Restolibra que usan `git+ssh://` con una
  deploy key. El build del Dockerfile reescribe esas URLs a SSH en
  tiempo de build (`git config url."ssh://git@github.com/".insteadOf
  "https://github.com/"`, descartado antes de terminar la capa) para no
  tener que mantener dos manifiestos de dependencias. Como Gestiolibra
  necesita **dos** repos privados (LibraGenda + LibraCore) y GitHub no
  permite reusar una deploy key entre repos, se generó una deploy key
  nueva de solo lectura para LibraGenda (`id_ed25519_libragenda`,
  agregada por el usuario en GitHub) y se armó un ssh-agent persistente
  en el VPS con ambas claves cargadas (`agent-multi-libra.sock`) — un
  solo `--ssh default=<socket-del-agente>` en el build alcanza para las
  dos, sin tocar `libracore.provisioning.panel_admin.cmd_actualizar`
  (que sigue con un solo `--ssh default=<archivo>` hardcodeado, pensado
  para un único repo — funciona igual si `LIBRACORE_SSH_KEY` apunta al
  socket del agente en vez de un archivo de clave).
- Consecuencias: 17 tests nuevos (130 en total). Verificado con la
  suite completa (reruns para descartar el flake del reloj de WSL2) +
  end-to-end contra un archivo SQLite real aplicando `aplicar_plan_en_db`
  en vivo (Básico→Estándar, confirmando que los 403 cambian
  correctamente en cada salto de plan). Deploy real a producción (primer
  cliente de prueba en el VPS) documentado por separado una vez
  completado — ver entrada siguiente o `TASKS.md`.

## ADR-014 — Deploy real verificado en el VPS: dos bugs invisibles en local

- Estado: aceptada
- Fecha: 2026-07-22
- Contexto: cerrando ADR-013, se hizo el primer build de Docker y la
  primera alta de cliente real en el VPS (nunca antes probado — no hay
  Docker en el entorno de desarrollo local en WSL). Aparecieron dos
  bugs reales, ninguno cubierto por la suite de tests local porque
  ambos solo existen en la capa de infraestructura de deploy:
  1. **Auth SSH con agente multi-key**: GitHub autentica la conexión
     SSH completa con la primera key del agente que acepte, y no
     reintenta con otra si esa key no tiene acceso al repo pedido. El
     ssh-agent persistente del VPS (`agent-multi-libra.sock`, con las
     deploy keys de LibraCore y LibraGenda cargadas, ver ADR-013) hacía
     que la key de LibraCore autenticara primero el transporte y el
     clone de LibraGenda fallara con `Repository not found` — con
     identidad de transporte correcta pero sin permiso a nivel de repo.
     Arreglado en el `Dockerfile`: cada dependencia usa su propio alias
     de `Host` SSH (`github-libracore`/`github-libragenda`) con
     `IdentitiesOnly yes` + su public key específica horneada en la
     imagen (las public keys no son secreto), forzando qué identidad
     del agente se ofrece por alias — sin tocar
     `libracore.provisioning` ni el ssh-agent del VPS.
  2. **Contrato de env vars de `libracore.provisioning`**: el
     `docker-compose.yml` que genera para cada cliente usa el mismo
     contrato genérico que ya leen Contalibra/Restolibra directamente
     (`DATA_DIR`/`ADMIN_USER`/`ADMIN_PASSWORD`/`ADMIN_NOMBRE`/
     `SECRET_KEY`/`DOCS_AUTH_SECRET`) — no el `DATABASE_URL`/
     `GESTIOLIBRA_*` que usa el `docker-compose.yml` de *dev* de este
     repo (escrito antes de conocer ese contrato). El primer contenedor
     de cliente crasheaba con `KeyError: DATABASE_URL`. Arreglado en
     `app/asgi.py`: deriva `DATABASE_URL`/`GESTIOLIBRA_LIBRACORE_DB_PATH`
     de `DATA_DIR` y mapea `ADMIN_USER`/`ADMIN_PASSWORD` a los nombres
     que ya lee `create_app()`, solo cuando `DATA_DIR` está presente —
     el `docker-compose.yml` de dev (que setea `DATABASE_URL`/
     `GESTIOLIBRA_*` explícito) sigue funcionando sin cambios.
  Efecto de paso: la propia clonación del repo Gestiolibra al VPS
  necesitó también su propia deploy key dedicada
  (`id_ed25519_gestiolibra`, solo lectura, agregada por el usuario) —
  separada de las dos que autentican las dependencias durante el build,
  siguiendo el mismo patrón que Contalibra (deploy key dedicada para el
  propio repo) en vez del PAT embebido en la URL que usa Restolibra.
- Consecuencias: imagen `gestiolibra:latest` construida con éxito vía
  `panel_admin.py actualizar` (el mismo comando que un deploy real
  usaría). Cliente de prueba (`prueba`, puerto 8076, plan Premium)
  provisionado con `nuevo_cliente.py`/`crear_cliente()`: contenedor
  healthy, tablas creadas (`Base.metadata.create_all()`, sin correr las
  cadenas de Alembic — mismo criterio ya documentado en `README.md` como
  "demo only" pero suficiente para un archivo SQLite nuevo), plan
  aplicado a mano (ver limitación de `_esperar_db_lista()` en
  `TASKS.md`), login admin verificado. Queda corriendo en el VPS como
  evidencia del pipeline completo. Ninguno de los dos bugs requirió
  tocar `libracore.provisioning` ni ningún código compartido con
  Contalibra/Restolibra.

## ADR-015 — Dashboard: sumar facturación/caja

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: facturación/caja quedó explícitamente fuera del primer corte
  del dashboard (ADR-012) a pedido del usuario. Quedó anotado en
  `TASKS.md` como pendiente concreto, reutilizando
  `libracore.db.caja.get_caja_resumen()` (ya genérico, mismo criterio
  que excluye movimientos `cuenta_corriente` que usa
  `get_facturas_filtradas` para saber si una factura está cobrada).
- Decisión: `DashboardService.summary()` agrega una clave `facturacion`
  con `facturas_emitidas_en_periodo` (vía
  `libracore.db.facturas.get_facturas_filtradas(desde, hasta,
  limit=0)["total"]` — `limit=0` evita traer y parsear filas, el conteo
  ya viene de un `COUNT(*)` separado) y `caja` (ingresos/egresos/saldo
  del período + saldo total acumulado, vía `get_caja_resumen()`). Ambas
  funciones son de `libracore.db`, sqlite3 crudo con conexión global ya
  configurada por `app/services/billing.py` al arrancar la app —
  `DashboardService` las llama directo, sin inyectar ninguna
  dependencia nueva (mismo patrón que `billing.py` ya usa). No se
  agregó gating explícito por módulo "facturacion" dentro del
  dashboard: en el diseño actual de planes (ADR-013), "facturacion" y
  "dashboard" solo existen juntos (ambos exclusivos de Premium), así
  que si el endpoint es alcanzable, facturación también está habilitada
  — no hay combinación de plan real donde eso no valga hoy.
- Consecuencias: 1 test nuevo (131 en total), verificado además
  end-to-end contra un archivo SQLite real (turno completado con precio
  configurado → factura emitida → dashboard del día refleja la factura
  y el ingreso de caja correspondiente).

## ADR-016 — Branding y dominio por cliente: dominio+SSL real, sin código nuevo

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: siguiente ítem de Fase 3 en `ROADMAP.md`, sin alcance
  detallado (mismo patrón que "onboarding multi-negocio" antes de
  ADR-013). Investigado antes de codificar: la maquinaria de dominio+SSL
  por cliente (`scripts/npm_api.py`/`npm_setup.py`, wrappers sobre
  `libracore.npm_api`/`libracore.provisioning.nuevo_cliente._setup_npm_proxy`)
  ya existía completa desde la ronda de onboarding multi-negocio — nunca
  se había ejercido contra la instancia real de NPM. "Branding" más allá
  de dominio+SSL no aplica: Contalibra/Restolibra tienen logo por
  instancia + paleta de color hardcodeada por producto, ninguno
  configurable por cliente, y ambos requieren un frontend que Gestiolibra
  no tiene — se descartó como fuera de alcance.
- Decisión: reutilizar la instancia de NPM ya usada por Contalibra/
  Restolibra (mismo VPS, mismas credenciales admin) en vez de levantar
  una nueva — se copió su `scripts/.npm_config.json` a Gestiolibra tal
  cual, sin generar credenciales nuevas. Se armó `dev.gestiolibra.com.ar`
  (dominio ya registrado con un wildcard DNS `*.gestiolibra.com.ar` ya
  apuntando a este VPS, confirmado con `nslookup` — no hizo falta tocar
  DNS) → proxy host + certificado Let's Encrypt real, mismo patrón que
  `dev.contalibra.com.ar`/`dev.restolibra.com.ar`.
- **Hallazgo real al crear el primer proxy**: copiar el
  `.npm_config.json` de Contalibra trajo también su valor de
  `forward_host` (`"contalibra-dev"`, un nombre de contenedor que no
  significa nada para Gestiolibra) — el primer proxy quedó mal apuntado
  y hubo que borrarlo y recrearlo. Investigando el motivo se confirmó
  que NPM y los contenedores de producto comparten la misma red docker
  (`stack_stack-net`), así que el proxy correcto apunta directo al
  **nombre del contenedor** en su **puerto interno** (`gestiolibra-dev`,
  `8000`) — no a una IP de gateway + el puerto publicado al host. Se
  corrigió el `forward_host` guardado en la config de Gestiolibra a la
  gateway real de esa red (`172.18.0.1`) en vez del nombre de contenedor
  heredado, aunque **ese campo no es realmente el mecanismo correcto para
  el flujo automático de alta de cliente real**: `_setup_npm_proxy()` en
  `libracore.provisioning.nuevo_cliente` arma el proxy con
  `forward_host_from_config()` (un valor fijo) + el puerto **publicado al
  host** del cliente (ej. `8076`) — para que eso funcione de verdad
  necesitaría ser `172.18.0.1:<puerto publicado>`, no
  `<nombre-de-contenedor>:8000` (que sí funciona, pero requeriría pasar
  el nombre de cada contenedor, no un `forward_host` fijo). No se tocó
  `libracore.provisioning` — mismo criterio que otros hallazgos en código
  compartido esta sesión: se documenta en `TASKS.md`, no se arregla sin
  necesidad concreta (ninguno de los tres productos onboardeó todavía un
  cliente real vía este flujo automático).
- Consecuencias: `dev.gestiolibra.com.ar` sirviendo tráfico real por
  HTTPS con certificado Let's Encrypt válido (verificado con `curl`,
  200 en `/health`), sin cambios de código en el repo (`.npm_config.json`
  vive gitignoreado, igual que en Contalibra/Restolibra). Un certificado
  huérfano (del primer intento mal configurado) quedó sin borrar en
  NPM — `NPMClient` no expone un método para eliminar certificados,
  y no vale la pena tocar la API cruda por un residuo sin costo ni
  efecto funcional.

## ADR-017 — Cierre de Fase 3: flujo automático de dominio verificado + backups probados

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: pedido explícito del usuario de cerrar la Fase 3. De los
  cuatro ítems, dos eran cerrables con trabajo de ingeniería sin
  depender de un cliente real: verificar el flujo *automático* de
  dominio+SSL (no el armado a mano de ADR-016) y verificar backups. El
  cuarto ítem ("validación con primeros negocios reales") no se puede
  cerrar así — necesita un negocio real usando el producto, y hoy no
  hay ninguno (ni frontend para que lo use sin llamar la API a mano).
  Se lo dejó explícitamente abierto en `ROADMAP.md` en vez de forzar un
  cierre artificial.
- Decisión — dominio automático: se corrigió el entendimiento de
  ADR-016. Con el `forward_host` de `scripts/.npm_config.json` apuntando
  a la gateway real de `stack_stack-net` (`172.18.0.1`, no el valor
  copiado de Contalibra ni el default de la librería), se invocó
  directamente `libracore.provisioning.nuevo_cliente._setup_npm_proxy()`
  — la misma función que usa `crear_cliente(domain=..., setup_npm=True)`
  para un alta real — contra el cliente `prueba`
  (`prueba.gestiolibra.com.ar` → proxy + certificado Let's Encrypt,
  puerto 8076 publicado al host). Funcionó sin ningún workaround ni
  código nuevo, confirmando que el hallazgo de ADR-016 era un valor de
  configuración copiado mal, **no un bug de `libracore.provisioning`** —
  se corrige esa lectura en `TASKS.md`/wiki.
- Decisión — backups: probado de punta a punta contra el cliente
  `prueba` (ya existía la maquinaria, `libracore.provisioning.
  panel_admin.cmd_backup`/`cmd_restore_db`, sin código nuevo): fila
  marcadora insertada → `panel_admin.py backup prueba` (tar.gz completo
  + copia WAL-safe de la DB) → datos mutados a propósito (fila borrada +
  fila espuria insertada) → `panel_admin.py restore-db prueba
  <backup>` → confirmado que la fila marcadora original vuelve, la
  mutación desaparece, y el contenedor queda sano tras el reinicio que
  hace el propio comando.
- Consecuencias: Fase 3 queda con 3 de 4 ítems completos
  (onboarding multi-negocio, branding y dominio por cliente, deploy/CI/
  backups) y el cuarto (validación con negocios reales) explícitamente
  abierto y fuera del alcance de una sesión de ingeniería — depende de
  que exista un negocio real, o de decidir construir un frontend
  primero. Ningún cambio de código en el repo en esta ronda.

## ADR-018 — Lectura de catálogo (branches/resources/services/clients) abierta a staff

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: al construir el frontend (ver ADR-019), la página de agenda
  necesita listar recursos/servicios/clientes para armar los selectores
  del formulario de turno — pero los cuatro routers de catálogo
  (`branches`, `resources`, `services`, `clients`) estaban montados
  enteros con `dependencies=[Depends(require_admin)]`, incluidas sus
  rutas `GET`. Un usuario `staff` (que el modelo de roles ya distingue
  explícitamente para manejar su propia agenda, ver `app/auth.py`)
  recibía 403 al intentar leer el catálogo, aunque sí puede crear/
  confirmar/cancelar/completar turnos. Consultado con el usuario antes
  de tocar permisos.
- Decisión: en los cuatro routers, el punto de montaje en `app/main.py`
  pasa de `admin_only` a `staff_or_admin_catalog` (`require_staff` —
  que ya significa "admin o staff", pese al nombre). Cada endpoint
  mutante (`POST`/`PUT`/`DELETE`) de esos cuatro archivos ahora declara
  `dependencies=[Depends(require_admin)]` explícito en el propio
  decorador, sumándose al del router (FastAPI acumula dependencias, no
  las reemplaza) — el resultado neto es lectura abierta a staff+admin,
  escritura solo admin. `branch_hours`, `service_prices`, `availability`,
  `business_settings` y `users` quedan sin cambios (admin-only
  completo) — no los necesita el MVP de agenda.
- Consecuencias: 4 tests nuevos (uno por router, confirmando 200 en
  lectura / 403 en escritura para staff) + 1 test existente corregido
  (`test_staff_can_manage_own_appointments_but_not_catalog` asumía la
  restricción vieja). 135 tests en total.

## ADR-019 — Frontend: SPA en React+Vite, MVP de login + agenda

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: cerrada la Fase 3 (ver ADR-017), el usuario pidió arrancar
  un frontend para destrabar "validación con negocios reales" — hasta
  ahora Gestiolibra era, deliberadamente, una API JSON pura sin ninguna
  página (`app/auth.py` explica por qué: los 401/403 planos en vez de
  redirects a `/login` fueron una decisión consciente para una API, no
  un descuido). Se consultó con el usuario antes de codificar: tipo de
  frontend (SPA en React+Vite separada — primera vez en la familia,
  vs. server-rendered Jinja2 como Contalibra/Restolibra) y alcance del
  MVP (login + agenda/turnos, dejando clientes/dashboard/facturación
  para después).
- Decisión — ubicación y stack: `frontend/` dentro de este mismo repo
  (un solo lugar para versionar API+UI), React 19 + TypeScript + Vite,
  `react-router-dom` para las dos rutas (`/login`, `/agenda`). Sin
  librería de componentes ni CSS framework — alcance chico, CSS propio
  minimal.
- Decisión — auth y same-origin: la SPA consume la API existente tal
  cual (cookie de sesión `gl_session`, sin tocar `libracore.auth`).
  Para que la cookie funcione sin pelear con CORS/`SameSite` cross-origin
  (complejidad real: cookies de sesión cross-origin necesitan
  `SameSite=None; Secure`, HTTPS obligatorio incluso en dev), se
  mantiene todo en el mismo origen en ambos entornos: en dev, el proxy
  de Vite (`vite.config.ts`, lista explícita de prefijos de la API)
  reenvía las llamadas al backend FastAPI corriendo aparte; en
  producción, el build de la SPA (`frontend/dist`) se sirve desde el
  mismo proceso FastAPI (`app/asgi.py` monta `/assets` como estáticos +
  una ruta catch-all `GET /{full_path:path}` que sirve `index.html`
  para cualquier ruta no reconocida por la API, registrada *después* de
  `create_app()` así los routers de la API siempre matchean primero).
  El mount se salta solo si `frontend/dist` no existe, así que
  `uvicorn app.asgi:app` local sin buildear el frontend sigue
  funcionando como API pura.
- Decisión — build en Docker: stage nuevo `frontend-build` (imagen
  `node:20-slim`, no viaja a la imagen final) que corre `npm ci && npm
  run build`; la imagen final de Python solo copia `frontend/dist` ya
  compilado. `.dockerignore` nuevo excluye `frontend/node_modules`/
  `frontend/dist` del contexto de build (no tiene sentido copiar un
  build local viejo ni instalar node_modules dos veces).
- **Hallazgo real en el camino** (ver ADR-018): construir la agenda
  reveló que `branches`/`resources`/`services`/`clients` eran
  admin-only incluso en lectura, un gap real del diseño de roles
  para un usuario `staff` — resuelto ahí, no en este ADR.
- Consecuencias: MVP verificado manualmente end-to-end en el browser
  real (no solo con `pytest`, que no cubre el frontend): login como
  admin y como staff, catálogo cargando en los selectores para ambos
  roles, alta de turno, y el ciclo completo confirmar→completar
  reflejando el estado en la tabla sin recargar la página. Sin errores
  de consola. `npm run build` (`tsc -b && vite build`) sin errores de
  tipos. Deploy real a `dev.gestiolibra.com.ar` documentado por
  separado una vez verificado el build de Docker — ver `TASKS.md`.

## ADR-020 — Deploy real del frontend: bind mount de dev tapaba el build

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: primer build real de la imagen con el stage de node
  (ADR-019) en el VPS. El build de Docker terminó sin errores (incluido
  el stage `frontend-build`), pero al levantar el contenedor
  `gestiolibra-dev`, cualquier ruta que no fuera de la API devolvía 404
  en vez de la SPA — `docker exec gestiolibra-dev ls /app/frontend/dist`
  confirmó que el directorio ni existía dentro del contenedor en
  ejecución, pese a haberse copiado correctamente durante el build.
- Causa raíz: `docker-compose.yml` de este servicio de dev monta
  `./:/app` (bind mount del checkout completo del host, necesario para
  que `--reload` de uvicorn vea cambios de código Python en vivo) — ese
  mount se superpone a **todo** `/app` dentro del contenedor, incluido
  `/app/frontend/dist`, que en el host **no existe** (es un artefacto de
  build, gitignoreado, generado solo dentro del stage de node del
  Dockerfile). El bind mount reemplazaba el build horneado en la imagen
  por un directorio vacío del host.
- Decisión: agregar `/app/frontend/dist` como volumen anónimo en
  `docker-compose.yml`, listado *después* del bind mount — Docker
  superpone volúmenes en orden, así que ese subpath específico preserva
  el contenido de la imagen en vez de heredar el vacío del bind mount de
  arriba, sin perder el hot-reload de Python para el resto de `/app`.
  No afecta los `docker-compose.yml` que genera
  `libracore.provisioning.nuevo_cliente` para clientes reales —esos
  montan solo `./data`, nunca el código completo—, así que este bug era
  exclusivo del contenedor de dev de este repo.
- Consecuencias: verificado en `dev.gestiolibra.com.ar` real (HTTPS,
  certificado válido): `/` sirve `index.html` de la SPA, `/assets/*.js`
  sirve los estáticos (200), `/health` sigue respondiendo como API
  (200), una ruta de cliente inexistente para el backend
  (`/agenda`) cae en el fallback y también sirve la SPA (200) para que
  `react-router-dom` la resuelva del lado del cliente. Probado además
  en el browser real: la página de login carga y el flujo de error
  (credenciales inválidas) se muestra correctamente, sin errores de
  consola. Cierra el ítem "en curso" de `TASKS.md` para el MVP del
  frontend.

## ADR-021 — Frontend: extender con Clientes y Dashboard

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: el usuario pidió extender el MVP del frontend (ADR-019,
  login + agenda) con las dos superficies que ya estaban listadas como
  "después del MVP": clientes y dashboard.
- Decisión — layout compartido: se extrajo `src/components/Layout.tsx`
  (header con nombre/rol/logout + navegación) de `Agenda.tsx`, para no
  repetir esa cabecera en cada página nueva. El link "Dashboard" del
  nav solo se muestra si `user.role === "admin"` — evita que un usuario
  staff navegue a una página que de entrada le va a devolver 403 (el
  endpoint ya es admin-only + gateado por plan, ver ADR-012/ADR-013).
- Decisión — página Clientes: lista siempre visible para staff+admin
  (mismo criterio de ADR-018: lectura de catálogo abierta a ambos
  roles). El formulario de alta/edición y los botones de
  eliminar/editar solo se renderizan si `user.role === "admin"` — la UI
  refleja exactamente el gating que ya existe en el backend
  (`POST`/`PUT`/`DELETE /clients` admin-only), no inventa una regla
  nueva.
- Decisión — página Dashboard: mismo diseño que el backend expone
  (`GET /dashboard`) sin agregar cálculos propios del lado del cliente
  — turnos por estado, clientes activos/nuevos, recordatorios/señas,
  facturación/caja (moneda formateada con `Intl.NumberFormat("es-AR",
  {style:"currency", currency:"ARS"})`). Un 403 (rol no-admin, o módulo
  "dashboard" no habilitado en el plan del cliente — ver ADR-013) se
  muestra como un mensaje explicativo en la página en vez de un error
  crudo, ya que es una condición esperada, no un bug.
- Consecuencias: verificado manualmente en el browser real con ambos
  roles: staff ve Clientes de solo lectura y no ve el link Dashboard en
  el nav; admin tiene alta/edición/baja de clientes completa (probado
  contra la API real: crear, editar teléfono, eliminar) y el dashboard
  muestra datos reales del rango seleccionado. Sin errores de consola.
  `npm run build` sin errores de tipos. Sin cambios en el backend — el
  MVP anterior (ADR-018) ya había resuelto el único gap de permisos que
  hacía falta.

## ADR-022 — El fix de ADR-020 (volumen anónimo) congelaba el frontend en el primer build

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: el usuario reportó que `dev.gestiolibra.com.ar`, después de
  loguearse, seguía mostrando el layout viejo (sin nav, sin las páginas
  de Clientes/Dashboard) pese a que ADR-021 ya se había desplegado con
  un rebuild + recreate aparentemente exitoso. Investigando: el archivo
  JS servido (`index-CvAcwije.js`, 239 KB) coincidía con el **primer**
  build del frontend (el de ADR-019/ADR-020), no con el build actual
  (`index-BeEH0MKe.js`, 246 KB, confirmado corriendo `npm run build`
  local). Un rebuild con `--no-cache` sí generó el bundle correcto —
  pero **después de recrear el contenedor con esa imagen, `/app/
  frontend/dist` seguía teniendo el archivo viejo**.
- Causa raíz: el volumen anónimo agregado en ADR-020
  (`- /app/frontend/dist` en `docker-compose.yml`, para que el bind
  mount `./:/app` no tapara el build con el directorio vacío del host)
  tiene un problema de fondo que no se vio en su momento porque nunca
  se probó un *segundo* rebuild real: Docker solo siembra un volumen
  anónimo con el contenido de la imagen **la primera vez que se crea**
  — en cualquier recreate posterior, sea cual sea el contenido nuevo de
  la imagen, Compose reutiliza el volumen ya existente tal cual quedó.
  El fix de ADR-020 no reparó el bind mount, lo reemplazó por un
  congelamiento silencioso en la versión del primer build.
- Decisión: el `Dockerfile` ahora copia el resultado del stage de node
  a `/opt/frontend-dist`, **fuera** del árbol `/app` que bind-montea el
  compose de dev — sidestepea el problema de raíz en vez de intentar
  preservar nada con un volumen. `app/asgi.py` busca primero en
  `/opt/frontend-dist` (la ubicación que hornea el Dockerfile) y cae a
  `frontend/dist` relativo al repo (para levantar el build local sin
  Docker, ej. tras correr `npm run build` a mano). El volumen anónimo
  de ADR-020 se eliminó de `docker-compose.yml`.
- Consecuencias: verificado con un rebuild `--no-cache` + recreate real
  contra el VPS — el bundle servido coincide con el hash del build
  recién generado (`index-BeEH0MKe.js`), no con ningún build anterior.
  135 tests de backend sin cambios (el problema era exclusivamente de
  la capa de infraestructura de Docker, no de código Python). Lección
  para la familia: un volumen anónimo no es un mecanismo válido para
  "preservar contenido de una imagen que un bind mount taparía" más
  allá del primerísimo build — cualquier producto que reutilice este
  patrón (Contalibra/Restolibra, si alguna vez agregan un stage de
  build tipo node/frontend a su propio contenedor de dev) debería
  copiar el artefacto fuera del árbol bind-monteado desde el principio.

## ADR-023 — Ruta `/dashboard` del frontend colisionaba con el endpoint `GET /dashboard` de la API

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: verificando el fix de ADR-022, navegar directo (carga de
  página completa, no ruteo del lado del cliente) a
  `https://dev.gestiolibra.com.ar/dashboard` devolvía el JSON crudo de
  error de FastAPI (`date_from`/`date_to` faltantes) en vez de la SPA.
  `/agenda` y `/clientes` funcionaban bien con el mismo patrón de
  navegación directa.
- Causa raíz: la SPA y la API viven en el mismo origen y el mismo
  espacio de rutas (sin prefijo `/api`, ver ADR-019) — la página del
  frontend se llamó `/dashboard`, el mismo string exacto que el
  endpoint real `GET /dashboard`. Como los routers de la API se montan
  en `create_app()` **antes** que el catch-all de `app/asgi.py`, la
  ruta real de la API gana siempre que coincide exacto. Con ruteo del
  lado del cliente (click en el link del nav) nunca se nota, porque
  `react-router-dom` intercepta la navegación sin que el browser emita
  un GET nuevo — el bug solo aparece con una carga de página completa
  (URL escrita a mano, F5, un link externo).
- Decisión: renombrar la ruta de la SPA de `/dashboard` a `/reportes`
  (`App.tsx`, `Layout.tsx`) — el componente y el archivo siguen
  llamándose `Dashboard`/`Dashboard.tsx`, solo cambia la URL. La llamada
  a la API dentro de `Dashboard.tsx` (`GET /dashboard?date_from=...`)
  no cambia, es el endpoint real. No se tocó la API ni se le agregó un
  prefijo `/api` general (cambio mucho más grande, afectaría todo lo ya
  documentado/probado) — un rename puntual del lado del frontend
  alcanza para las tres páginas que existen hoy.
- Consecuencias: `/agenda`, `/clientes` y `/reportes` verificados con
  navegación directa (carga completa) sin colisión. Riesgo que queda
  documentado para el futuro: cualquier página nueva del frontend cuyo
  nombre de ruta coincida exacto con un path de nivel superior ya
  existente en la API (`auth`, `branches`, `resources`, `services`,
  `clients`, `business`, `users`, `reminders`, `deposits`, `config`,
  `dashboard`, `appointments`, `health`) va a pisarse de la misma
  forma — revisar esta lista antes de nombrar una ruta nueva de la SPA.

## ADR-024 — Client.id se genera solo si no se manda

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: el usuario notó que el formulario de alta de cliente del
  frontend pedía un `id` a mano — a diferencia de sucursales/recursos/
  servicios (catálogo que un admin arma una vez, con slugs pensados
  deliberadamente), los clientes se dan de alta todo el tiempo durante
  la operación diaria; pedirle a quien atiende que invente un
  identificador único para cada cliente nuevo es fricción real sin
  ningún beneficio (el cliente no lo ve ni lo necesita en ningún lado).
- Decisión: `ClientCreate.id` pasa de obligatorio a opcional
  (`str | None = None`) en `app/routers/clients.py`. Si se omite,
  `create_client()` genera uno con `uuid4()`. Sigue aceptándose
  explícito si se manda (uso scripteado/pruebas que ya lo pasan, sin
  romper nada existente). No se tocó `libragenda.Client` (el dominio
  compartido no exige ni prohíbe ningún formato de id más allá de "no
  vacío") ni el resto del catálogo (`branches`/`resources`/`services`
  siguen pidiendo id explícito a propósito — los arma un admin una sola
  vez, no es la misma fricción). El campo "ID" se sacó del formulario
  de alta del frontend (`Clientes.tsx`); edición nunca lo mostró.
- Consecuencias: 1 test nuevo (136 en total — confirma que dos altas
  sin id consecutivas generan ids distintos). Verificado manualmente en
  el browser: alta de cliente sin ningún campo de id, confirmado por
  API que se generó un UUID real y quedó guardado correctamente.

## ADR-025 — Rediseño visual del frontend: Tailwind CSS + shadcn/ui

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: el usuario pidió un frontend "más llamativo", mostrando
  como referencia un dashboard admin con sidebar de navegación, cards
  con sombra, badges de estado, avatar, etc. (estilo shadcn/ui). Se
  consultaron dos decisiones antes de tocar código: stack de estilos
  (Tailwind CSS + shadcn/ui, el stack real de la referencia, vs. CSS
  propio imitando el look) y alcance (layout + las 3 páginas existentes,
  sin sumar elementos nuevos de producto como buscador/notificaciones/
  toggle de tema — eso no existía antes y no se pidió).
- Decisión — stack: Tailwind CSS v4 (`@tailwindcss/vite`, sin
  `tailwind.config.js` ni PostCSS separado — la v4 se configura desde
  el propio `vite.config.ts` + `@theme` en CSS) + componentes shadcn/ui
  (`npx shadcn@latest add ...`, código fuente propio en
  `src/components/ui/`, no una dependencia de npm con lógica oculta —
  así funciona shadcn por diseño). Alias de import `@/*` → `src/*`
  agregado en `vite.config.ts` + ambos `tsconfig*.json` (requerido por
  las convenciones de shadcn). `npx shadcn@latest init` no funcionó de
  entrada (necesita Tailwind + alias ya configurados para detectarlos)
  — se armó `components.json` a mano con la config por defecto
  ("new-york", neutral, CSS variables) y se instalaron los componentes
  directo, sin pasar por el wizard interactivo.
- Decisión — layout: `Layout.tsx` reemplaza el nav superior por un
  `Sidebar` colapsable (componente `sidebar.tsx` de shadcn, el más
  completo de la librería — incluye modo mobile con `Sheet`, atajo de
  teclado, persistencia de estado en cookie). Mismo contenido que antes
  (Agenda/Clientes/Dashboard, Dashboard oculto para staff) más logo,
  avatar con iniciales del usuario, y logout como ícono en vez de botón
  de texto — matching la referencia.
- Decisión — páginas: `Login` como `Card` centrada; `Agenda`/`Clientes`
  usan el componente `Table` de shadcn + `Badge` para estado (turnos:
  variante por estado; clientes: activo/inactivo) + `Select` de Radix
  en vez de `<select>` nativo; `Dashboard` como grid de `Card`s
  (`CardDescription`/`CardTitle` grande/detalle), con `Skeleton` en vez
  de "Cargando…" en texto plano. Mismo comportamiento y llamadas a la
  API que antes — cambio puramente visual, sin tocar lógica de negocio
  ni el backend.
- Consecuencias: `npm run build` sin errores de tipos (tsconfig
  necesitó sacar `baseUrl` — deprecado en la versión de TypeScript de
  este proyecto, `paths` solo alcanza sin él). Verificado manualmente
  en el browser: estilos de Tailwind/shadcn confirmados por
  `getComputedStyle` (border-radius, box-shadow, colores reales, no
  clases sin efecto), sidebar colapsa/expande correctamente, las tres
  páginas renderizan con la nueva UI sin errores de consola. 136 tests
  de backend sin cambios (ninguno tocado en esta ronda). Deploy real al
  VPS pendiente, ver `TASKS.md`.

## ADR-026 — Normalizar el stack de frontend: TanStack Table + React Hook Form + Zod

- Estado: aceptada
- Fecha: 2026-07-23
- Contexto: el usuario propuso un stack de frontend estándar para la
  familia (FastAPI/REST, React, Tailwind, shadcn/ui, Lucide — ya en uso
  desde ADR-019/ADR-025 — más TanStack Table y React Hook Form + Zod,
  que Gestiolibra todavía no usaba: las tablas eran HTML plano con los
  primitivos de shadcn sin lógica de sorting, y los formularios eran
  `useState` controlado a mano sin validación declarativa). Pidió
  migrar Agenda/Clientes para que el stack real coincida con el
  declarado, no solo parcialmente.
- Decisión — tablas: `src/components/data-table.tsx` nuevo, wrapper
  genérico y reutilizable sobre `@tanstack/react-table` (lógica de
  sorting vía `useReactTable`/`getSortedRowModel`) + los primitivos
  `Table`/`TableHeader`/`TableBody`/`TableRow`/`TableCell` de shadcn
  (presentación) — un componente único en vez de repetir el mismo
  boilerplate en cada página. `sortableHeader(label)` (helper también
  en ese archivo) arma un botón de header ordenable con ícono
  `ArrowUpDown` de lucide-react, reutilizado en ambas tablas migradas.
- Decisión — formularios: `src/components/ui/form.tsx` (componente
  shadcn oficial para React Hook Form: `Form`, `FormField`, `FormItem`,
  `FormLabel`, `FormControl`, `FormMessage`) + un schema `zod` por
  formulario (`clientSchema` en `Clientes.tsx`, `appointmentSchema` en
  `Agenda.tsx`) resuelto vía `@hookform/resolvers/zod`. Mismos campos y
  mismo payload enviado a la API que antes — el cambio es puramente de
  mecanismo de formulario (validación declarativa por campo, mensajes
  de error automáticos) y de tabla (sorting), no de reglas de negocio
  ni de contrato con el backend.
- Consecuencias: verificado manualmente en el browser — validación de
  Zod mostrando "El nombre es obligatorio"/"Email inválido"/"Elegí un
  servicio/cliente/horario" campo por campo; alta de cliente y de turno
  exitosas después de corregir los errores (confirmado contra la API
  real); sorting de la columna "Nombre"/"Horario" invierte el orden
  correctamente al hacer click dos veces. Sin errores de consola.
  `npm run build` sin errores de tipos (el bundle creció a ~552 KB
  gzip ~169 KB por las librerías nuevas — advertencia de tamaño de
  Vite, no un error; no se hizo code-splitting todavía, queda anotado
  en `TASKS.md` si hace falta más adelante). 136 tests de backend sin
  cambios (ninguno tocado en esta ronda).

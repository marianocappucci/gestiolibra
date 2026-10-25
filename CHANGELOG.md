# Changelog — Gestiolibra

## [Unreleased]

- **El modo sin conexión: atender y cobrar un turno en el nodo de LibraEdge** (2026-10-25; ADR-036; plan «GestioLibra, MedLibra y LibraDesk en la versión de escritorio», PR 9). Pines: **libragenda `v0.15.0`** (antes `v0.14.0`; `atencion_en_nodo`, migración `0011` aditiva), **libraedge `v0.23.0`** (dependencia nueva; su repo es público: sin deploy key en el CI ni en el build) y **libra-ui `v0.181.0`** (antes `v0.180.0`). **Migración propia `0010_libraedge`** (aditiva; las tablas del nodo, en toda instancia). Una instancia sin nodo y el central **no cambian**: la agenda trae tres campos de más, neutros.
  - **El nodo (la PC del local sin internet):** la agenda es de **sólo consulta** (dar, confirmar, reprogramar y cancelar turnos, el catálogo, la configuración, las señas y los usuarios dan 409 `solo_en_el_central`), pero un turno ya dado se marca **en curso** (`POST /appointments/{id}/start`), **«no vino»** (`/no-show`) o **completado** (`/complete`, que cobra). Completar hace, en **una sola transacción**, la atención (`libragenda.atencion_en_nodo` → `turno.atendido`), la seña y el saldo en la caja (`caja.movimiento`, con la misma referencia que en la web y sin factura) y el pedido de la factura en la cola de ARCA; si el turno no se puede atender no queda nada. Con conexión la factura sale en el acto; sin ella queda en cola, sale sola al volver, y el cliente se lleva el **comprobante no fiscal** (`GET /appointments/{id}/comprobante-no-fiscal`: «NO VÁLIDO COMO FACTURA — La factura se emite al volver la conexión»).
  - **El central:** `/sync/v1/*` con un despachador que aplica `turno.atendido` (idempotente; si el turno cambió en la web, **la atención y lo cobrado valen** y queda «a revisar»), `caja.movimiento`, `cola.pedido`, `gestio.factura_turno` (la factura con su número y CAE; si el turno ya tiene otra, revisión manual) y `gestio.cliente_alta`. Lista «Turnos a revisar»: `GET /api/nodo/turnos-a-revisar` y `POST .../revisar` (sólo el central). «Sucursal sin internet» (`/api/nodos-offline`), el canje del código y la cola de comprobantes (`/api/nodo/cola`) se montan sólo con una base (ADR-035).
  - **Clientes provisorios:** el cliente nuevo del nodo recibe un id `"-N"` (`AltaEnNodo(..., id_de_texto=True)`), el central lo deduplica por CUIT (nunca por nombre ni teléfono) y le asigna su uuid; `client_billing` (CUIT y condición de IVA) viaja en la misma operación.
  - **Pantallas** (sin cambios fuera de un nodo): cartel «Sin conexión» e ítem «Cola de comprobantes» (`/cola`, `BandejaDeLaCola`), sólo en un nodo; la agenda sin «Nuevo turno» ni confirmar, reprogramar o cancelar, y con «En curso», «No vino» y «Completar»; aviso de la factura en cola y enlace al comprobante; las etiquetas «Atendido sin conexión» y «A revisar»; el panel «Turnos a revisar» (en la web, con «Ya lo revisé»); «Provisorio» en Clientes; «Sucursal sin internet» en Configuración. El cartel tiene **texto propio**: `TEXTO_CARTEL_SIN_CONEXION_CON_COLA` del kit habla de cartas de porte y CPE (es de LibraCargo).
  - **Al desplegar:** `libragenda-migrar upgrade` y `alembic upgrade head` (ya están en el compose y en `panel_admin.py`) **antes** de arrancar la app nueva: la agenda lee `agenda_applied_attendances`. Primero los motores, después el central, después los nodos.
  - **Para el instalador (PR 12):** `instalador/productos/gestiolibra.json` con las tablas espejo de `app.offline.TABLAS_DE_REFERENCIA`, las de sólo lectura (`TABLAS_SOLO_LECTURA`) y las altas (`ALTAS_EN_EL_NODO`: `agenda_clients` con ids de texto), las cuatro cadenas en orden (`libragenda-migrar`, `libraauth-migrar --base core`, `libracore-migrar`, `alembic`), `DATABASE_URL` (la leen `libragenda-migrar` y `alembic`) y las variables `LIBRAEDGE_NODE_ID` y `LIBRAEDGE_ESTADO`. **Sin carga inicial** (`LIBRAEDGE_CARGA_INICIAL` no se declara: la autoridad del nodo nace vacía). **Falta decidir:** los datos de la empresa (`config.json`, no es una tabla) no se espejan, así que el encabezado del comprobante no fiscal sale vacío hasta que el instalador los siembre o `generar_ticket_venta` acepte una config; y el nombre de la sucursal para `--sucursal`.
  - **Rinde sólo con el plan Premium** (el módulo `facturacion` es de Premium): sin él completar un turno sólo marca la atención.
  - Tests: ver ADR-036. Backend `tests/test_nodo_*.py` y `tests/test_migracion_libraedge.py` (PostgreSQL real, receptor y despachador reales, dobles de ARCA y del ticket prestado); frontend `src/test/nodo-sin-conexion.test.tsx`. `tests/test_modulos_renombrados.py` mide hasta su revisión (`0009`) y no hasta `head`.

- **Una sola base: se va la variable del core, el alta nace con `gestiolibra` y nada más, y la suite también** (2026-10-25; ADR-035; plan «GestioLibra, MedLibra y LibraDesk en la versión de escritorio», PR 6). **Sin migración, sin cambio de pin** (libracore `v1.194.0` ya estaba). `nuevo_cliente.py` y `panel_admin.py`: `tabla_modulos="gestiolibra_modulos"` y fuera `base_core_separada=True`; el compose de dev pierde `GESTIOLIBRA_LIBRACORE_DB_PATH` y el montaje de `docker/postgres-init` (`10-base-de-libracore.sql` se borra); CI y smoke sin `gestiolibra_core`; la suite pasa a una base por worker.
  - **`libraauth-migrar` se queda en `--base core`** (el plan decía `--base dominio`): medido que en una instancia de dos bases (la demo) `--base dominio` crea las tablas de auth vacías en el dominio y deja la unión imposible (`auth_en_los_dos`). Con una base los dos valores van al mismo lugar; se cambia cuando la demo esté unida.
  - **Al desplegar:** dev (ya unida): retirar el override temporal del VPS; el cambio de compose recrea `gestiolibra-postgres` (unos segundos). Demo: nada hasta que se una. `scripts/reset_demo.sh` y `app/config.py` siguen aceptando las dos formas.
  - **No incluye** pasar las filas de `gestiolibra_modulos` a la `modulos` del motor (ADR-034, punto 3): queda para un PR aparte.
  - Tests: `tests/test_migraciones_en_el_deploy.py` (las cuatro cadenas corridas de verdad sobre una base nueva sin variable del core, destino de `libraauth` con una y dos bases, `--base dominio` sobre dos bases deja la unión imposible), `tests/test_una_sola_base.py` (dos bases con una base propia descartable) y `tests/test_config_backup.py`.

- **Preparado para una sola base: `agenda_clients`, `gestiolibra_modulos` y una `Config` de una base o de dos** (2026-10-25; ADR-034; plan «GestioLibra, MedLibra y LibraDesk en la versión de escritorio», PR 3). Pin **libragenda `v0.14.0`** (antes `v0.13.0`): `clients` pasa a `agenda_clients` y la tabla de versión es `alembic_version_libragenda` (ADR-017 y ADR-018 de libragenda). **Con migración propia, `0009_gestiolibra_modulos`**: renombra la `modulos` del producto (la del motor se llama igual) sin tocar filas. **No une ninguna instancia.**
  - **Al desplegar:** `libragenda-migrar upgrade` ANTES de arrancar la app (con el pin nuevo y la base sin migrar, `create_all` crea una `agenda_clients` vacía y la migración aborta); después `alembic upgrade head`. Los dos ya están en el `command:` del compose de dev y en `panel_admin.py actualizar`. `scripts/reset_demo.sh` (que ahora cuenta `agenda_clients`) y la imagen van juntos.
  - `ClientBillingRow` y la revisión `0003` apuntan a `agenda_clients.id`. `app/database.py` (el contrato `get_modulos`/`set_addon` del backoffice) y `plans.aplicar_plan_en_db` leen y escriben `gestiolibra_modulos` por `ModuleRepository`.
  - `app/config.py`: la base de LibraCore es la de `GESTIOLIBRA_LIBRACORE_DATABASE_URL` (o la histórica `..._DB_PATH`) si es OTRA base y, si no, la del dominio; el respaldo no vuelca dos veces la misma. `scripts/reset_demo.sh` hace lo mismo.
  - Las filas de `gestiolibra_modulos` pasan a la `modulos` del motor **en el PR de «se va la variable del core»** (la sentencia está probada en `tests/test_modulos_renombrados.py`). Hasta entonces una alta nueva por el provisioning del motor queda incompleta (espera la tabla `modulos` en el dominio): sin clientes reales ni altas previstas.
  - Tests: `tests/test_modulos_renombrados.py` (cadena real sobre PostgreSQL: base nueva, una sola base con la `modulos` del motor, instancia de antes, downgrade) y `tests/test_una_sola_base.py` (`Config` y la app entera con una base y con dos).

- **La barra de estado del pie** (2026-10-20; pedido del humano; libracore ADR-075, libra-ui ADR-083; sin migración). Una línea chica al pie de todas las pantallas con el usuario, el certificado de ARCA que vence en menos de 30 días o venció, el último respaldo y la versión (este producto no tiene LibraEdge: esa parte no se muestra). `app/main.py` monta `build_estado_del_sistema_router` del motor (`GET /api/estado-del-sistema`, con `require_staff`: cualquier rol de la instancia; ARCA, respaldo y versión del motor, sólo el admin) con la carpeta de respaldos. Frontend: `createLayout({ barraDeEstado })`. Tests: `tests/test_estado_del_sistema.py`. Pines: **libracore `v1.187.0`** (antes `v1.186.2`) y **libra-ui `v0.170.0`** (antes `v0.168.0`; trae también el ADR-084 del kit, «Sucursal sin internet» dice que en el local se entra por la copia local). Sin migración.

- **Dar de alta al cliente desde «Nuevo turno»** (2026-10-16; ADR-071 de libra-ui, ADR-033 de este producto). Pin **libra-ui `v0.158.1`** (antes `v0.157.0`; suma `SelectCliente` y el guard `auditoria-de-clientes`). El campo «Cliente» del diálogo «Nuevo turno» es ahora `SelectCliente`: el buscador de siempre con el botón «Agregar nuevo cliente» (nombre, teléfono y email); el creado se suma a la lista y queda elegido. Un helper compartido (`payloadDeCliente` en `src/api.ts`) arma el payload de `POST /clients` para este selector y para la página Clientes. Test de comportamiento (`src/test/agenda-nuevo-cliente.test.tsx`) y guard de fuentes (`src/test/campos-de-cliente.test.ts`).
  - **Permiso (decisión del humano): el personal `staff` puede dar de alta clientes.** `POST /clients` pasa de admin-only a staff+admin; `PUT` y `DELETE /clients/{id}` siguen siendo sólo de admin. Sin migración. Tests: `tests/test_clients.py` (el staff crea un cliente y recibe 403 al editarlo o borrarlo; sin sesión, 401).
- Pines: **libracore `v1.173.0`** (antes `v1.170.0`) y **libra-ui `v0.156.0`** (antes `v0.153.0`); libraauth sigue en `v0.51.0`. **Sin migración.** libracore `v1.171.0` (ADR-058): un cobro de factura no puede superar lo que falta (409). `v1.172.0` (ADR-059 y ADR-060): las notas de crédito con CAE restan de lo pendiente y el cobro entra por el turno de caja desde el motor. `v1.173.0` (ADR-061, `libracore.demo`): una demo no habla con ARCA ni muestra datos fiscales reales. libra-ui `v0.154.0` (sin desbordes a 390 px, contraste AA), `v0.155.0` (ADR-068: «Acreditada» y «pendiente» del motor) y `v0.156.0` (ADR-069: el error de la consulta de CUIT lleva al tutorial de Padrón A13). Efecto en este producto: ninguno en el cobro, que no monta `build_comprobantes_router` y registra los movimientos de caja de un turno completado por el total de la factura que acaba de emitir.
- **Botón «Consultar en ARCA» en el alta de un cliente.** `app/main.py` monta `build_consultar_cuit_router` del motor (`GET /api/consultar-cuit/{cuit}`): completa razón social, domicilio y condición de IVA desde el padrón (`ws_sr_padron_a13`). Sin certificados, 503; si ARCA no delegó el servicio, 403 con el paso a seguir y un enlace «Cómo habilitarlo» al tutorial de Configuración → Integraciones. El componente propio repite la URL del tutorial porque libra-ui `v0.156.0` no exporta `URL_TUTORIAL_PADRON` (está en `src/configuracion/arca-tutorial.ts`, sin entrada en `exports`).
- **La demo no queda con datos fiscales reales** (ADR-061). Tests de la semilla con `libracore.demo` (`auditar_literales` sobre el texto y `auditar_datos_fiscales` sobre la base) en `tests/test_seed_demo.py`.
- Pines: **libracore `v1.170.0`** (antes `v1.168.0`), **libraauth `v0.51.0`** (antes `v0.50.0`) y **libra-ui `v0.153.0`** (antes `v0.152.1`). **Sin migración.** libracore `v1.169.0` suma `soltar_fk` (ADR-056; sin efecto en este producto, la usa LibraDesk). libracore `v1.170.0`: `delete_client` bloquea la baja de un cliente con cuenta corriente (`cc_pagos`, `cc_debitos`, `recibos` y `cc_asientos` con rol cliente; ADR-057) con un `ValueError` que dice que se puede desactivar. libraauth `v0.51.0`: el responsable puede aceptar por adelantado la próxima versión de los Términos (ADR-024). libra-ui `v0.153.0`: tras el gate de Términos, un aviso no bloqueante «Aceptar / Más tarde» (tarjeta abajo a la derecha, ADR-066). Efecto en este producto: ninguno en la baja de clientes, que sale por el catálogo de libragenda y no por `delete_client` del motor.
- **Listo para varios procesos y registro de errores de la familia** (2026-10-13; ADR-044 y ADR-045 de libracore, ADR-023 de libraauth, ADR-053 de libra-ui). Pines: **libracore v1.159.0** (antes `v1.157.0`, sin migración), **libraauth v0.50.0** (antes `v0.49.0`, **migración `0003_captcha_usados`**: el compose de dev, `scripts/panel_admin.py` y `scripts/nuevo_cliente.py` ya corren `libraauth-migrar upgrade` antes de arrancar y `exigir_schema_al_dia` la exige) y **libra-ui v0.142.1** (antes `v0.141.0`); piso `uvicorn>=0.30`.
  - **Varios procesos por instancia (`uvicorn --workers N`), sin prenderlos: todo sigue en 1.** `WEB_CONCURRENCY` por defecto es 1 y el compose de dev pasa `--workers ${WEB_CONCURRENCY:-1}` (el `CMD` del `Dockerfile` queda igual: uvicorn ya respeta `WEB_CONCURRENCY`). `create_app()` ES el arranque y lo corre cada worker: los «si no existe, crear» (módulos con `ensure_seeded()`, admin, usuario de la demo, migración de secretos, tablas de auditoría) van dentro de `una_vez_al_arrancar("gestiolibra-arranque")`, de a un proceso por vez, y cada paso sigue preguntando adentro. El anti-replay del captcha del login se anota en la base de `usuarios` (`app.state.captcha` con `UsadosEnBase`) en vez de en la memoria del proceso. Los engines (el de auth y el del dominio, que arma `libragenda`) llevan `pool_pre_ping=True`: **tras un restore en caliente con más de un worker, reiniciar el contenedor.**
  - **Registro de errores.** `instalar_registro_de_errores(app, "gestiolibra")` junto a `SecurityHeadersMiddleware`: un 500 responde `{"detail": "Error interno", "ref": "<8 hex>"}` y deja una línea en `DATA_DIR/errores/errores.jsonl`; `POST /api/errores-cliente` (público a propósito) recibe los errores del navegador. En `main.tsx`, `instalarReporteDeErrores()` antes de montar y `<ErrorBoundary>` alrededor de toda la app; el proxy de dev de Vite suma `/api/errores-cliente`. El compose de `-dev` suma `LIBRA_ENTORNO=dev`, `LIBRA_INSTANCIA=gestiolibra-dev` y `LIBRA_VERSION`.
  - Tests nuevos: `tests/test_registro_de_errores.py`, el replay del captcha contra la base (`tests/test_captcha_login.py`) y `tests/test_varios_procesos.py` (`uvicorn --workers 2` de verdad; marca `varios_procesos`). El doble del captcha de `tests/conftest.py` acepta ahora `(request, usados)`, como llama el router desde libraauth v0.50.0.
- **libra-ui `v0.125.0`** (2026-10-07; antes `v0.123.0`) y el catálogo de íconos de identidad de la familia (ADR-035 del kit). El menú y los títulos de pantalla toman el ícono de `ICONOS.<concepto>` (`libra-ui/iconos-identidad`) en vez de un `lucide` elegido a mano; `/usuarios`, `/logs` y `/configuracion` ya no pasan `icono` porque el default del kit es el del catálogo. **Ningún ícono cambia**: los siete conceptos del menú (dashboard, agenda, señas, clientes, usuarios, log de actividad y configuración) ya coincidían con el catálogo. Suma `test/iconos-del-catalogo.test.ts`, que falla si una entrada del menú se aparta del catálogo o un título lo escribe con otro ícono. Sin migración ni cambio de backend.
- **libracore `v1.141.0`** (2026-10-06; antes `v1.140.0`). El emisor de los PDF se resuelve por documento (ADR-031 del motor): config de la instancia, después el `emisor_id` del comprobante, después lo que aporte el producto; acepta el logo como contenido (`logo_bytes`). El archivo de la factura lleva el id, así una nota de crédito no pisa a su factura. Sin migración; para quien no aporta nada, los PDF salen iguales.
- **libracore `v1.140.0`** (2026-10-06; antes `v1.139.0`). Suma la pre factura del motor (ADR-030): documento no fiscal con número interno, PDF y envío por correo, sobre la bandeja de comprobantes. **Con migración del motor**: `0021_pre_factura`, que agrega columnas vacías a `comprobantes_pendientes`. La bandeja de siempre no cambia.
- **libracore `v1.139.0`** (2026-10-06; antes `v1.138.0`). La cuenta corriente de clientes se lee **sólo** del libro (ADR-029 del motor): se retiran el saldo calculado y el interruptor `LIBRACORE_CC_DESDE_EL_LIBRO`. Sin migración. Lo cargado por fuera de los escritores del motor se ve después de `libro_de_clientes.reconstruir()`.
- **libracore `v1.138.0`** (2026-10-06; antes `v1.137.1`). Las lecturas de la cuenta corriente de clientes pueden salir del libro (ADR-028 del motor), detrás del interruptor por instancia `LIBRACORE_CC_DESDE_EL_LIBRO`, **apagado por defecto**: sin encenderlo no cambia nada. Sin migración.
- **libracore `v1.137.1`** (2026-10-06; antes `v1.136.1`). La cuenta corriente de clientes también como libro, **en sombra** (`libracore.db.libro_de_clientes`, ADR-027 del motor): los escritores del motor asientan cada pago, débito, cobro a cuenta y venta fiada en `cc_asientos`, y el saldo se sigue leyendo calculado. **Con migración del motor**: `0020_origen_del_asiento`, que agrega una columna vacía. La `v1.137.1` no rompe una base sin `cc_asientos`.
- **libracore `v1.136.1`** (2026-10-06; antes `v1.135.0`). Suma el libro de cuenta corriente de terceros, opcional (`cc_asientos` y `libracore.db.libro_de_terceros`, ADR-026 del motor). **Con migración del motor**: `0019_libro_de_terceros`, que crea una tabla vacía y deja `cc_asientos.created_at` y `cierres_diarios.created_at` en hora de Argentina. Este producto no lo usa: su comportamiento no cambia.

- **libracore `v1.135.0`** (2026-10-05; antes `v1.134.0`). Las funciones del comprobante aceptan `conn=` para emitir dentro de la transacción del producto (ADR-025 del motor; sin `conn`, nada cambia) y el dinero del motor se guarda exacto en PostgreSQL (ADR-024): **migración `0018` del motor**, que pasa 33 columnas de dinero de `DOUBLE PRECISION` a `NUMERIC` sin redondear. La lectura sigue siendo `float`: el comportamiento de este producto no cambia.

- **libracore `v1.134.0`** (2026-10-05; antes `v1.132.0`). Trae el emisor opcional de cada comprobante (`facturas.emisor_id`, ADR-021 del motor), la anulación con rastro de un comprobante sin CAE (`POST /api/facturas/{id}/anular`, ADR-022) y el registro con número tipeado (ADR-023); incluye v1.133.0 (`libracore.spa`, la SPA del motor, que este producto no adopta todavía). **Con migración del motor**: `0016` y `0017` (columnas nuevas en `facturas` y el índice de numeración por emisor y ambiente); las aplica el arranque (`init_core_schema`) y `alembic upgrade head`. Para este producto no cambia el comportamiento: no pasa emisor.

- **libracore `v1.132.0`** (2026-10-05; antes `v1.131.0`). Suma `libracore.arca_wsfecred` (consultas al registro de FCE de ARCA) y `GET /api/facturas/fce/corresponde` (¿a esta factura le corresponde ser FCE?, para avisar antes de emitir; ADR-019 del motor). Nada cambia en la emisión. Sin migración.

- **libracore `v1.131.0`** (2026-10-05; antes `v1.127.0`). Trae la **nota de crédito parcial** con tope acumulado (v1.130.0: `{"importe": ...}` en `POST /api/facturas/{id}/nota-credito`; sin él, la total de siempre), la marca de cada nota en la cuenta corriente (v1.128.0), `build_nota_de_credito_router` (v1.129.0) y la nota total de una FCE frenada antes de ir a ARCA (v1.131.0). Cambia sólo `notas_de_credito` y `facturas_router`. Sin migración.

- **libracore `v1.126.0`** (2026-10-04; antes `v1.124.0`). Suma el nucleo `libracore.notas_de_credito` (este producto todavia no lo usa); la guarda del CUIT del receptor deja de bloquear las notas (ARCA autoriza la nota de credito a un CUIT que no cierra, igual que la factura), e incluye v1.125.0 (los routers de libracore rechazan booleanos en los campos numericos). Sin migración.

- **libracore `v1.124.0`** (2026-10-04; antes `v1.123.0`). La guarda del CUIT del receptor (`arca_wsfe.problema_del_receptor`, que `solicitar_cae` corre antes de llamar a ARCA): CUIT de 11 digitos en clase A y FCE, y verificador valido en toda clase. El endpoint de notas no lo monta este producto. Sin migración.

- **libracore `v1.109.0` y libra-ui `v0.73.2`** (2026-09-17). La copia externa
  del backup sale cifrada con `rclone crypt`, o no sale —eso corre en el host y
  ya está desplegado ahí—. Lo que llega con este pin: la pantalla *Datos /
  Backup* nombra la **clave privada de ARCA** y dice que la copia externa va
  cifrada; el estado deja de dar "al día" una copia que subió sin cifrar; y el
  botón de backup arma el mismo ZIP que el cron (todas las carpetas de `data/`,
  `arca_certs/` incluida). Como el pin de `libra-ui` venía de `v0.72.1`, trae
  además lo de `0.73.0` y `0.73.1`: el aviso en un modal cuando el ticket no se
  puede imprimir, y las fechas `dd-mm-aaaa` en los listados de comercio.

- **Reprogramar un turno y las señas, con pantalla**: los dos tenían endpoint
  desde el MVP y ninguna pantalla. En el detalle del turno de la agenda,
  **Reprogramar** mueve el turno a otro horario (`POST
  /appointments/{id}/reschedule`) mandando la hora de pared sin huso, como el
  alta, y muestra tal cual el 409 del backend (choque, fuera de horario). Sólo
  cambia el horario: el motor reprograma sobre el mismo recurso. En el mismo
  detalle, la **seña** del turno: pedirla (admin y staff) y, sólo admin,
  cobrarla con su medio de pago, marcarla fallida o devolverla. Pantalla nueva
  **Señas** (`/senas`, admin-only, en el menú junto a la Agenda) con las
  pendientes, cobradas, devueltas y fallidas, y el contador "Señas pendientes"
  del Dashboard lleva ahí. Para eso hizo falta un endpoint: `GET /deposits`
  (`?status=` opcional, admin + módulo `senas`), que devuelve cada seña con su
  turno pegado encima y ordenadas por el turno más próximo; antes una seña sólo
  se podía ver conociendo su turno. 7 tests de backend y 24 de frontend nuevos
  (94 en total).
- **La copia externa se enlaza desde Configuración, como add-on
  `resguardo_externo`**: se monta `build_resguardo_enlace_router` de LibraCore
  v1.93.0 (`/api/config/resguardo-externo/enlace`) sobre la misma carpeta de
  backups que el router de backup, detrás de admin y del add-on. El add-on
  (`plans.ADDONS`) está disponible en cualquier plan, viene **apagado** y se
  prende por instancia desde el backoffice. 🔴 Hizo falta tocar
  `ModuleRepository.is_enabled`: devolvía `True` para todo lo que no estuviera
  en `TODOS_LOS_MODULOS`, así que un add-on nunca daba 403. Ahora un add-on
  está prendido sólo con fila y `habilitado` verdadero; los módulos de plan
  siguen igual. Y se crea `app/database.py` con `get_modulos()`/`set_addon()`,
  el contrato que el backoffice invoca por `docker exec` — apuntado a la base
  del dominio, no a la de LibraCore que la app configura en `billing`.
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

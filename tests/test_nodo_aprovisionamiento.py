"""El reparto de autoridad del nodo: qué espeja, qué no escribe, qué da de alta (ADR-036).

La declaración de `app/offline.py` se mide contra la base de verdad (la que dejan las cuatro cadenas del deploy): una tabla
que ya no existe, una clave foránea que sale del espejo o una referencia sin clave foránea a un cliente son defectos que
no dan error en la app: aparecen en el local, sin conexión, con la PC ya instalada.
"""
from __future__ import annotations

from libracore.db import core
from nodo_apoyo import NODO

from app import offline


def tablas_de_la_base():
    with core.get_connection() as conn:
        return {f[0] for f in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()").fetchall()}


def claves_foraneas():
    """`[(tabla_hija, columna, tabla_padre)]` de toda la base."""
    with core.get_connection() as conn:
        return [tuple(f) for f in conn.execute(
            """SELECT cl.relname, att.attname, fcl.relname
                 FROM pg_constraint c
                 JOIN pg_class cl ON cl.oid = c.conrelid
                 JOIN pg_class fcl ON fcl.oid = c.confrelid
                 JOIN pg_namespace n ON n.oid = cl.relnamespace
                 JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
                WHERE c.contype = 'f' AND n.nspname = current_schema()""").fetchall()]


def test_toda_tabla_de_referencia_existe_en_la_base(admin_client):
    faltan = offline.TABLAS_DE_REFERENCIA - tablas_de_la_base()
    assert not faltan, f"tablas de referencia que la base no tiene (el espejo no las puede bajar): {sorted(faltan)}"


def test_el_nodo_no_espeja_lo_que_genera_ni_lo_que_no_usa(admin_client):
    """Lo que el nodo genera sube como operaciones y no baja (el central se lo devolvería y el nodo se pisaría), y las claves
    de ARCA y de la instancia no salen del VPS."""
    prohibidas = {
        "caja_movimientos", "facturas", "cola_arca", "agenda_node_attendances", "turnos_caja", "cc_asientos",
        "arca_credenciales_servicio", "secretos_instancia", "auth_log", "envios_email", "mp_pagos", "mp_movimientos",
        "sent_reminders", "actividad_log", "sync_outbox", "sync_inbox", "node_identity", "clients",
        # Los avisos (ADR-040): el registro lleva el teléfono y el texto de cada cliente, y los manda el central (un nodo no manda).
        "avisos_envios",
    }
    assert not offline.TABLAS_DE_REFERENCIA & prohibidas


def test_los_avisos_son_del_central_y_la_tabla_existe_en_la_base(admin_client):
    """`avisos_envios` es de un solo lado: el central manda (y registra), el nodo no manda ni espeja. Si alguien la suma al espejo, el
    nodo bajaría los teléfonos y los textos de los clientes de todas las sucursales, y el registro del central se pisaría con el del nodo."""
    assert "avisos_envios" in tablas_de_la_base(), "el motor ya no crea la tabla: este test mide una que no existe"
    assert "avisos_envios" not in offline.TABLAS_DE_REFERENCIA
    assert "avisos_envios" not in offline.aprovisionamiento.nombres


def test_la_lista_a_revisar_baja_al_nodo_y_la_atencion_propia_no(admin_client):
    assert "agenda_applied_attendances" in offline.TABLAS_DE_REFERENCIA
    assert "agenda_node_attendances" not in offline.TABLAS_DE_REFERENCIA
    assert "agenda_applied_attendances" in offline.TABLAS_SOLO_LECTURA


def test_ninguna_clave_foranea_del_espejo_apunta_a_una_tabla_que_el_nodo_no_tiene(admin_client):
    """Si una tabla espejada tiene una clave foránea a otra que no se espeja, el nodo no puede aplicar el cambio del central
    (la fila padre no existe) y el ciclo se traba."""
    sueltas = [(hija, col, padre) for hija, col, padre in claves_foraneas()
               if hija in offline.TABLAS_DE_REFERENCIA and padre not in offline.TABLAS_DE_REFERENCIA]
    assert not sueltas, f"claves foráneas del espejo hacia fuera del espejo: {sueltas}"


def test_el_nodo_escribe_los_clientes_provisorios_y_ninguna_otra_tabla_del_espejo(admin_client):
    """`agenda_clients` se guarda pero deja pasar los ids provisorios; `client_billing` queda sin guarda porque el nodo
    escribe la fila de su cliente provisorio. Todo lo demás del espejo es de sólo lectura (usuarios, términos y cajas son un
    upsert idempotente del arranque, ver `app/offline.py`)."""
    assert "agenda_clients" in offline.TABLAS_SOLO_LECTURA
    assert "client_billing" not in offline.TABLAS_SOLO_LECTURA
    assert {a.tabla for a in offline.aprovisionamiento.altas} == {"agenda_clients"}
    (alta,) = offline.aprovisionamiento.altas
    assert alta.id_de_texto is True, "los ids de la agenda son texto: el provisorio es «-N» y el mapeo es el de texto"
    assert {"libraedge_mapeo", "libraedge_mapeo_texto"} <= offline.aprovisionamiento.solo_lectura
    assert {"libraedge_mapeo", "libraedge_mapeo_texto"} <= offline.aprovisionamiento.nombres


def test_ninguna_columna_apunta_a_un_cliente_de_la_agenda_sin_clave_foranea(admin_client):
    """LibraEdge reapunta por las claves foráneas del catálogo; una columna de cliente SIN clave foránea quedaría apuntando
    al id provisorio para siempre. Hoy no hay ninguna que declarar (`AltaEnNodo` sin `referencias`): este test avisa el día
    que aparezca una."""
    fks = {(hija, col) for hija, col, _padre in claves_foraneas()}
    with core.get_connection() as conn:
        columnas = [tuple(f) for f in conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND column_name IN ('client_id', 'cliente_id', 'customer_id')").fetchall()]
    sin_fk = [(t, c) for t, c in columnas if (t, c) not in fks and t in offline.TABLAS_DE_REFERENCIA]
    assert not sin_fk, f"columnas de cliente sin clave foránea en tablas espejadas: {sin_fk}"
    # Y las que sí tienen clave foránea hacia `agenda_clients` son las que el espejo reapunta solo.
    hijas = sorted(h for h, _c, p in claves_foraneas() if p == "agenda_clients")
    assert hijas == ["appointments", "client_billing"]


def test_registrar_el_nodo_lo_deja_activo_con_su_secreto_y_su_prefijo(escenario):
    e = escenario
    ((identidad, sucursal),) = e.sql_central("SELECT node_id, branch_id FROM node_identity WHERE active = 1")
    assert (identidad, sucursal) == (NODO, "sucursal-1")
    assert e.prefijo and e.secreto


def test_las_sucursales_son_las_de_la_agenda(escenario):
    e = escenario
    with core.conectar(e.url_central) as conn:
        assert offline.listar_sucursales(conn) == [{"id": "sucursal-1", "nombre": "Sucursal Centro", "activa": True}]


def test_un_segundo_nodo_en_la_misma_sucursal_no_se_registra(escenario):
    import pytest
    from libraedge import aprovisionamiento as aprov

    e = escenario
    with core.conectar(e.url_central) as conn:
        with pytest.raises(aprov.SegundoNodoEnLaSucursal):
            aprov.registrar(conn, offline.aprovisionamiento, "otro-local", sucursal="sucursal-1")


def test_un_nodo_no_siembra_los_modulos_ni_crea_un_admin_local(monkeypatch):
    """En un nodo los módulos son los del central (`gestiolibra_modulos` se espeja de sólo lectura) y los usuarios también
    (libraauth ADR-027): sembrarlos al arrancar chocaría con la guarda de LibraEdge, o crearía un `admin` con otro id. Es el
    arranque de la PC del local **antes de la primera sincronización**."""
    from motor_de_test import fresh_database_url

    from app.main import create_app

    monkeypatch.setenv("LIBRAEDGE_NODE_ID", NODO)
    app = create_app(fresh_database_url())
    try:
        assert app.state.modules.get_all() == {}
        assert app.state.users.get_by_username("admin") is None
    finally:
        app.state.auth_engine.dispose()


def test_fuera_de_un_nodo_el_arranque_si_los_siembra(monkeypatch):
    from motor_de_test import fresh_database_url

    from app.main import create_app

    app = create_app(fresh_database_url())
    try:
        assert app.state.modules.get_all(), "el control: la web arranca con sus módulos"
    finally:
        app.state.auth_engine.dispose()


def test_el_central_con_un_nodo_lo_cuenta_en_la_barra_de_estado(escenario):
    """El admin de la web ve cuántos nodos tiene su instancia (y si alguno se calló): `offline.nodos_del_central`."""
    e = escenario
    with e.en_el_central():
        estado = e.cliente.get("/api/estado-del-sistema").json()
    assert estado["libraedge"]["rol"] == "central" and estado["libraedge"]["nodos"] == 1


def test_el_cli_de_libraedge_llega_a_la_base_de_la_instancia(escenario, monkeypatch):
    """`libraedge-central` corre sin la app: abre la base por `GESTIOLIBRA_DATABASE_URL` (`offline._conectar`)."""
    e = escenario
    monkeypatch.setenv("GESTIOLIBRA_DATABASE_URL", e.url_central)
    conn = offline._conectar()
    try:
        assert offline.listar_sucursales(conn) == [{"id": "sucursal-1", "nombre": "Sucursal Centro", "activa": True}]
    finally:
        conn.close()

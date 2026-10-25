"""Los clientes que se dan de alta en el nodo sin conexión: id provisorio, alta en el central y vuelta (ADR-036).

Los ids de la agenda son de **texto** (un uuid): el id provisorio es el texto `"-N"` y su mapeo es `libraedge_mapeo_texto`
(libraedge v0.23, ADR-026). Un cliente son dos filas (`agenda_clients` y `client_billing`) y una sola operación.
"""
from __future__ import annotations

from libracore.db import core
from nodo_apoyo import NODO

from app import offline


def alta(e, **extra):
    cuerpo = {"name": "Beto Ruiz", "phone": "1155550000", "email": "beto@ejemplo.test"}
    cuerpo.update(extra)
    r = e.cliente.post("/clients", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


# ── En el nodo ────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_el_cliente_del_nodo_nace_con_un_id_provisorio_y_queda_en_el_outbox(escenario):
    e = escenario
    c = alta(e, cuit="20222333445", condicion_iva="Responsable Inscripto")
    assert c["id"] == "-1", "un id del central es un uuid: el del nodo es el texto «-N»"
    assert (c["name"], c["cuit"], c["condicion_iva"]) == ("Beto Ruiz", "20222333445", "Responsable Inscripto")
    # Las dos filas, con el mismo id provisorio.
    assert e.sql_nodo("SELECT id, name FROM agenda_clients WHERE id = '-1'") == [("-1", "Beto Ruiz")]
    assert e.sql_nodo("SELECT id, cuit FROM client_billing WHERE id = '-1'") == [("-1", "20222333445")]
    (operacion,) = e.pendientes()
    assert operacion.operation_type == "gestio.cliente_alta"
    assert operacion.aggregate_id == f"{NODO}:cliente:-1"
    assert operacion.payload["cliente_id"] == "-1" and operacion.payload["cuit"] == "20222333445"


def test_cada_alta_toma_el_siguiente_id_provisorio_y_nunca_lo_reusa(escenario):
    e = escenario
    assert [alta(e, name=f"Cliente {n}")["id"] for n in range(3)] == ["-1", "-2", "-3"]


def test_un_cliente_invalido_no_deja_ni_el_cliente_ni_la_operacion(escenario):
    e = escenario
    r = e.cliente.post("/clients", json={"name": "   ", "email": "no-es-un-correo"})
    assert r.status_code == 422, r.text
    assert e.sql_nodo("SELECT count(*) FROM agenda_clients WHERE id LIKE '-%'") == [(0,)]
    assert e.pendientes() == []


def test_un_id_que_pasa_el_cliente_se_ignora_en_el_nodo(escenario):
    e = escenario
    assert alta(e, id="mio")["id"] == "-1"


def test_editar_o_borrar_un_cliente_es_del_central_y_dice_por_que(escenario):
    e = escenario
    # Sin conexión: «esperá a que vuelva».
    r = e.cliente.put("/clients/ana", json={"name": "Ana G."})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_conexion"
    assert e.cliente.delete("/clients/ana").json()["detail"]["codigo"] == "sin_conexion"
    # Con conexión: «hacelo desde la web».
    e.en_linea(True)
    r = e.cliente.put("/clients/ana", json={"name": "Ana G."})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "solo_en_el_central"
    # Y uno provisorio no se edita ni con conexión: la operación que ya se encoló llevaría los datos viejos.
    provisorio = alta(e)["id"]
    r = e.cliente.put(f"/clients/{provisorio}", json={"name": "Otro nombre"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "solo_en_el_central"
    assert "todavía no subió" in r.json()["detail"]["mensaje"]
    assert e.sql_nodo("SELECT name FROM agenda_clients WHERE id = 'ana'") == [("Ana Gómez",)]


# ── En el central ─────────────────────────────────────────────────────────────────────────────────────────────────────


def test_el_central_crea_el_cliente_con_su_id_y_anota_el_mapeo(escenario):
    e = escenario
    alta(e, cuit="20222333445", condicion_iva="Responsable Inscripto")
    e.subir_todo_y_exigir()

    filas = e.sql_central("SELECT c.id, c.name, c.phone, b.cuit, b.condicion_iva FROM agenda_clients c "
                          "JOIN client_billing b ON b.id = c.id WHERE c.name = 'Beto Ruiz'")
    assert len(filas) == 1
    id_central, nombre, telefono, cuit, iva = filas[0]
    assert len(id_central) == 36 and not id_central.startswith("-"), "el central le asigna un uuid"
    assert (telefono, cuit, iva) == ("1155550000", "20222333445", "Responsable Inscripto")
    assert e.sql_central("SELECT id_central FROM libraedge_mapeo_texto WHERE node_id = ? AND tabla = ? AND id_nodo = ?",
                         NODO, "agenda_clients", "-1") == [(id_central,)]
    assert e.sql_central("SELECT count(*) FROM agenda_clients WHERE id LIKE '-%'") == [(0,)]


def test_subir_el_alta_dos_veces_no_duplica_al_cliente(escenario):
    e = escenario
    alta(e)
    operaciones = e.pendientes()
    e.subir(operaciones)
    e.subir(operaciones)
    assert e.sql_central("SELECT count(*) FROM agenda_clients WHERE name = 'Beto Ruiz'") == [(1,)]
    # Y aunque llegue de nuevo sin que el receptor la deduplique, el aplicador es idempotente por el mapeo.
    from app.services import clientes_nodo

    with core.conectar(e.url_central) as conn:
        clientes_nodo.aplicar_cliente_alta(conn, operaciones[0])
        conn.commit()
    assert e.sql_central("SELECT count(*) FROM agenda_clients WHERE name = 'Beto Ruiz'") == [(1,)]


def test_si_el_cuit_ya_estaba_cargado_se_une_a_su_ficha(escenario):
    e = escenario
    # El central ya tiene a Ana con ese CUIT, escrito con otros separadores.
    alta(e, name="Ana G.", cuit="27-11111111-3")
    e.subir_todo_y_exigir()
    assert e.sql_central("SELECT count(*) FROM agenda_clients WHERE active") == [(1,)], "no se duplicó"
    assert e.sql_central("SELECT id_central FROM libraedge_mapeo_texto") == [("ana",)]
    # El central es la autoridad del maestro: no se toca el nombre.
    assert e.sql_central("SELECT name FROM agenda_clients WHERE id = 'ana'") == [("Ana Gómez",)]


def test_el_nombre_o_el_telefono_solos_no_alcanzan_para_unir_dos_clientes(escenario):
    e = escenario
    alta(e, name="Ana Gómez", phone="1100000000", email=None)
    e.subir_todo_y_exigir()
    assert e.sql_central("SELECT count(*) FROM agenda_clients WHERE name = 'Ana Gómez'") == [(2,)]


def test_el_correo_une_pero_no_si_el_cuit_es_otro(escenario):
    e = escenario
    e.ejecutar_en_el_central("UPDATE agenda_clients SET email = 'ana@ejemplo.test' WHERE id = 'ana'")
    alta(e, name="Otra Ana", email="ANA@ejemplo.test", cuit="20999888771")
    e.subir_todo_y_exigir()
    # Mismo correo, CUIT distinto: son dos personas.
    assert e.sql_central("SELECT count(*) FROM agenda_clients WHERE active") == [(2,)]


def _operacion_de_alta(id_nodo: str, nombre: str, cuit: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        node_id=NODO, operation_type="gestio.cliente_alta", schema_version=1,
        payload={"version": 1, "cliente_id": id_nodo, "nombre": nombre, "telefono": None, "email": None, "cuit": cuit,
                 "condicion_iva": None, "activo": True, "creada_at": "2026-10-25T10:00:00+00:00"})


def test_un_id_provisorio_reusado_por_otra_persona_va_a_revision_manual(escenario):
    """Una PC reemplazada que arrancó la secuencia de cero con el mismo `node_id`: el `-1` ya era otro cliente, y un turno
    a ese id iría a una persona distinta."""
    e = escenario
    from app.services import clientes_nodo

    with core.conectar(e.url_central) as conn:
        clientes_nodo.aplicar_cliente_alta(conn, _operacion_de_alta("-1", "Beto Ruiz", "20222333445"))
        conn.commit()
    with core.conectar(e.url_central) as conn:
        try:
            clientes_nodo.aplicar_cliente_alta(conn, _operacion_de_alta("-1", "Carla Díaz", "27333444556"))
        except clientes_nodo.ClienteDelNodoError as exc:
            assert "reusó el id provisorio -1" in str(exc)
        else:
            raise AssertionError("tendría que haber ido a revisión manual")


def test_un_alta_mal_formada_va_a_revision_manual_y_no_traba_la_cola(escenario):
    e = escenario
    from app.services import clientes_nodo

    for payload in (
        {"version": 2},                                                       # versión que no entiende
        {"version": 1, "cliente_id": "55", "nombre": "x"},                    # no es un id provisorio
        {"version": 1, "cliente_id": "-1", "nombre": ""},                     # sin nombre
        {"version": 1, "cliente_id": "-1", "nombre": "x", "creada_at": "2026-10-25T10:00:00"},  # fecha sin zona
    ):
        operacion = _operacion_de_alta("-1", "x", "1")
        operacion.payload = payload
        with core.conectar(e.url_central) as conn:
            try:
                clientes_nodo.aplicar_cliente_alta(conn, operacion)
            except clientes_nodo.ClienteDelNodoError:
                pass
            else:
                raise AssertionError(f"tendría que haber rechazado {payload}")
            finally:
                conn.rollback()


# ── La vuelta al nodo: el espejo reapunta ─────────────────────────────────────────────────────────────────────────────


def test_el_espejo_cambia_el_provisorio_por_el_definitivo_y_no_deja_filas_huerfanas(escenario):
    """Lo que hace LibraEdge cuando baja el mapeo y la fila definitiva: reapunta las claves foráneas y borra la fila
    provisoria. `client_billing.id` es **a la vez clave primaria y clave foránea** de `agenda_clients.id`: se mide que no se
    quede una fila provisoria huérfana ni se pise la definitiva (el riesgo que el plan anotó para MedLibra con `patients`)."""
    from libraedge.sync import reconciliacion

    e = escenario
    alta(e, cuit="20222333445", condicion_iva="Responsable Inscripto")
    e.subir_todo_y_exigir()
    ((id_central,),) = e.sql_central("SELECT id_central FROM libraedge_mapeo_texto")

    # El espejo ya bajó la fila definitiva (con el cuerpo que escribió el central): las dos tablas.
    with core.get_connection() as conn:
        conn.execute("SET LOCAL libraedge.aplicando = '1'")
        conn.execute("INSERT INTO agenda_clients (id, name, phone, email, active) VALUES (?, ?, ?, ?, ?)",
                     (id_central, "Beto Ruiz", "1155550000", "beto@ejemplo.test", True))
        conn.execute("INSERT INTO client_billing (id, cuit, condicion_iva) VALUES (?, ?, ?)",
                     (id_central, "20222333445", "Responsable Inscripto"))
        espejadas = frozenset(t.nombre for t in offline.aprovisionamiento.tablas) - {"libraedge_mapeo"}
        resultado = reconciliacion.reapuntar(conn, "agenda_clients", "-1", id_central, espejadas=espejadas)
        conn.commit()
    assert resultado == reconciliacion.HECHO
    assert e.sql_nodo("SELECT count(*) FROM agenda_clients WHERE id = '-1'") == [(0,)]
    assert e.sql_nodo("SELECT count(*) FROM client_billing WHERE id = '-1'") == [(0,)]
    assert e.sql_nodo("SELECT cuit FROM client_billing WHERE id = ?", id_central) == [("20222333445",)]

"""Qué se puede hacer en un nodo y qué no (ADR-036).

La agenda del nodo es de **sólo consulta**: no se dan, mueven ni cancelan turnos (decisión del humano). El catálogo y la
configuración los manda el central. Lo que no se puede contesta **409** con un código que la pantalla distingue:
`solo_en_el_central` (no existe en el nodo, esté en línea o no) y `sin_conexion` (esperá a que vuelva).
"""
from __future__ import annotations

import pytest


def codigo(r):
    assert r.status_code == 409, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}"
    return r.json()["detail"]["codigo"]


# (método, ruta, cuerpo): lo que el nodo NO hace.
ESCRITURAS_DEL_CENTRAL = [
    ("POST", "/appointments", {"resource_id": "box-1", "service_id": "corte", "client_id": "ana",
                                "starts_at": "2099-01-02T10:00:00"}),
    ("POST", "/appointments/{turno}/confirm", None),
    ("POST", "/appointments/{turno}/cancel", {"reason": "x"}),
    ("POST", "/appointments/{turno}/reschedule", {"starts_at": "2099-01-03T10:00:00"}),
    ("POST", "/appointments/{turno}/deposit", {"amount": "100.00"}),
    ("POST", "/deposits/{turno}/mark-paid", None),
    ("POST", "/branches", {"id": "otra", "name": "Otra"}),
    ("PUT", "/branches/sucursal-1", {"name": "Otro nombre"}),
    ("DELETE", "/branches/sucursal-1", None),
    ("POST", "/resources", {"id": "box-2", "name": "Box 2", "branch_id": "sucursal-1"}),
    ("POST", "/services", {"id": "tintura", "name": "Tintura", "duration_minutes": 60}),
    ("PUT", "/services/corte/prices", {"branch_id": "sucursal-1", "price": "2000.00"}),
    ("POST", "/resources/box-1/availability", {"weekday": 1, "starts_at": "09:00:00", "ends_at": "18:00:00"}),
    ("PUT", "/config/arca", {"empresa": "negocio", "cuit": "20111222339", "punto_venta": 5}),
    ("POST", "/api/nodo/turnos-a-revisar/revisar", {"atenciones": ["x"]}),
    ("POST", "/users", {"username": "otro", "name": "Otro", "password": "clave-larga-1", "role": "staff"}),
]


@pytest.mark.parametrize(("metodo", "ruta", "cuerpo"), ESCRITURAS_DEL_CENTRAL)
def test_lo_que_manda_el_central_es_409_solo_en_el_central_en_un_nodo(escenario, metodo, ruta, cuerpo):
    e = escenario
    ruta = ruta.format(turno=e.datos["turno"])
    for en_linea in (False, True):
        e.en_linea(en_linea)
        r = e.cliente.request(metodo, ruta, json=cuerpo)
        assert codigo(r) == "solo_en_el_central", "esté en línea o no: el nodo no tiene esa función"
    assert e.pendientes() == [], "una función que el nodo no tiene no deja nada para subir"


def test_el_nodo_lee_todo_lo_que_espeja(escenario):
    e = escenario
    for ruta in ("/branches", "/resources", "/services", "/clients", "/clients/ana", "/services/corte/prices",
                 "/deposits", "/config/arca", "/medios-pago", "/api/nodo/turnos-a-revisar", "/api/nodo/cola",
                 "/api/estado-del-sistema"):
        r = e.cliente.get(ruta)
        assert r.status_code == 200, f"GET {ruta}: {r.status_code} {r.text}"
    r = e.cliente.get("/resources/box-1/agenda", params={"date_from": "2099-01-01", "date_to": "2099-01-02"})
    assert r.status_code == 200 and len(r.json()) == 3


def test_el_nodo_atiende_y_da_de_alta_clientes(escenario):
    """Lo que SÍ escribe un nodo: atender (en curso, completado, no vino) y el alta provisoria. Todo lo demás, arriba."""
    e = escenario
    assert e.cliente.post(f"/appointments/{e.datos['turno']}/start").status_code == 200
    assert e.cliente.post(f"/appointments/{e.datos['turno']}/complete", json={"medio_pago": "efectivo"}).status_code == 200
    assert e.cliente.post(f"/appointments/{e.datos['otro_turno']}/no-show").status_code == 200
    assert e.cliente.post("/clients", json={"name": "Nueva"}).status_code == 201


def test_la_barra_de_estado_dice_que_es_un_nodo_y_cuantas_facturas_esperan(escenario):
    e = escenario
    assert e.cliente.post(f"/appointments/{e.datos['turno']}/complete", json={"medio_pago": "efectivo"}).status_code == 200
    estado = e.cliente.get("/api/estado-del-sistema").json()
    assert estado["libraedge"]["rol"] == "nodo" and estado["libraedge"]["en_linea"] is False
    assert estado["libraedge"]["a_facturar"] == 1


def test_consultar_un_cuit_en_arca_es_del_central_aunque_sea_una_lectura(escenario):
    """Es un GET, pero usa el certificado de ARCA, que no existe en el nodo."""
    e = escenario
    assert codigo(e.cliente.get("/api/consultar-cuit/20111222339")) == "sin_conexion"
    e.en_linea(True)
    assert codigo(e.cliente.get("/api/consultar-cuit/20111222339")) == "solo_en_el_central"

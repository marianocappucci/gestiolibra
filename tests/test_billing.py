from fastapi.testclient import TestClient


def _seeded_appointment(
    client: TestClient, client_data: dict | None = None, price: str | None = "1000.00",
) -> str:
    client.post("/branches", json={"id": "branch-1", "name": "Sucursal demo"})
    client.post("/resources", json={"id": "resource-1", "name": "Box 1", "branch_id": "branch-1"})
    client.post("/services", json={"id": "service-1", "name": "Corte", "duration_minutes": 30})
    client.post("/clients", json=client_data or {"id": "client-1", "name": "Ana"})
    for weekday in range(7):
        client.post("/resources/resource-1/availability", json={
            "weekday": weekday, "starts_at": "00:00:00", "ends_at": "23:59:00",
        })
    if price is not None:
        client.put("/services/service-1/prices", json={"branch_id": "branch-1", "price": price})
    created = client.post("/appointments", json={
        "resource_id": "resource-1", "service_id": "service-1",
        "client_id": (client_data or {}).get("id", "client-1"), "starts_at": "2099-01-01T10:00:00",
    })
    assert created.status_code == 201, created.text
    appointment_id = created.json()["id"]
    confirmed = client.post(f"/appointments/{appointment_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return appointment_id


# ── ARCA: el router es el de LibraCore ───────────────────────────────────────
#
# Desde el 2026-08-30 `/config/arca` lo sirve `libracore.arca_router`, no un
# router propio. El comportamiento del router --que valide el certificado antes
# de escribirlo, que chequee que el par sea pareja, que sepa cuando vence-- lo
# prueba el motor en `tests/test_arca_router.py`; **lo que se prueba aca es el
# cableado**: que este producto lo monte, en esa ruta, y detras de su gate.
#
# 🔴 Los tests de esta seccion decian antes `certificado_path: "cert.crt"` en el
# cuerpo del PUT y pasaban. Siguen pasando hoy --el payload del motor ignora las
# claves de mas-- pero ya no significan lo mismo: el path lo pone el servidor al
# recibir el archivo. Un test que no distingue esas dos cosas es exactamente el
# que deja la migracion "verde" sin haber mirado nada.


def test_get_arca_config_defaults_to_none(admin_client: TestClient):
    response = admin_client.get("/config/arca")
    assert response.status_code == 200
    assert response.json() is None


def test_set_and_get_arca_config(admin_client: TestClient):
    client = admin_client
    set_response = client.put("/config/arca", json={
        "empresa": "negocio", "cuit": "20111222339", "punto_venta": 3,
        "ambiente": "homologacion",
    })
    assert set_response.status_code == 200
    assert set_response.json()["punto_venta"] == 3

    fetched = client.get("/config/arca")
    assert fetched.status_code == 200
    assert fetched.json()["cuit"] == "20111222339"

    updated = client.put("/config/arca", json={
        "empresa": "negocio", "cuit": "20111222339", "punto_venta": 5,
    })
    assert updated.status_code == 200
    assert updated.json()["punto_venta"] == 5


def test_el_certificado_ya_no_se_declara_por_json(admin_client: TestClient):
    """🔴 El path del certificado lo pone el SERVIDOR al recibir el archivo.

    Hasta hoy este endpoint aceptaba `certificado_path` en el cuerpo: una ruta
    del filesystem que el admin escribia y el servidor abria, apuntando a un
    archivo que alguien tenia que haber dejado dentro del volumen del
    contenedor a mano. El alta no se podia hacer desde el navegador.
    """
    admin_client.put("/config/arca", json={
        "empresa": "negocio", "cuit": "20111222339", "punto_venta": 3,
        "certificado_path": "/tmp/mio.crt", "clave_path": "/tmp/mia.key",
    })
    guardado = admin_client.get("/config/arca").json()
    assert guardado["certificado_path"] != "/tmp/mio.crt"
    assert guardado["clave_path"] != "/tmp/mia.key"
    # Y la pantalla se entera de que no hay nada cargado, en vez de mostrar dos
    # rutas que apuntan a archivos que no existen.
    assert guardado["tiene_certificado"] is False
    assert guardado["tiene_clave"] is False


def test_el_certificado_se_sube_y_se_valida_antes_de_escribirlo(admin_client: TestClient):
    """Subir el `.csr` --el pedido-- en vez del `.crt` que ARCA devuelve es el
    error habitual, y antes se aceptaba: fallaba recien al emitir el primer
    comprobante, con un error de ARCA que no hablaba de la causa."""
    respuesta = admin_client.post(
        "/config/arca/certificado",
        files={"archivo": ("pedido.pem", b"-----BEGIN CERTIFICATE REQUEST-----", "text/plain")},
    )
    assert respuesta.status_code == 422
    assert "certificado" in respuesta.json()["detail"].lower()


def test_el_estado_dice_si_la_instancia_puede_facturar(admin_client: TestClient):
    """🔑 Es el endpoint que trae el vencimiento del certificado, que es el dato
    que evita la falla silenciosa: duran dos anos y el dia que vencen la
    facturacion deja de andar sin que nadie haya tocado nada."""
    respuesta = admin_client.get("/config/arca/estado")
    assert respuesta.status_code == 200
    assert respuesta.json()["configurado"] is False


def test_las_rutas_nuevas_tambien_son_de_admin(staff_client: TestClient):
    """El gate del producto tiene que cubrir el router ENTERO, no solo el
    `GET`/`PUT` que ya existia. Subir un certificado es la accion mas sensible
    de esta pantalla."""
    assert staff_client.get("/config/arca/estado").status_code == 403
    assert staff_client.post("/config/arca/probar").status_code == 403
    assert staff_client.delete("/config/arca/credenciales").status_code == 403


def test_complete_without_price_configured_does_not_invoice(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client, price=None)
    response = client.post(f"/appointments/{appointment_id}/complete")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["factura"] is None


def test_complete_with_price_and_no_deposit_requires_medio_pago(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    response = client.post(f"/appointments/{appointment_id}/complete")
    assert response.status_code == 422


def test_complete_with_price_and_no_deposit_invoices_full_amount(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    response = client.post(
        f"/appointments/{appointment_id}/complete", json={"medio_pago": "efectivo"},
    )
    assert response.status_code == 200
    factura = response.json()["factura"]
    assert factura is not None
    assert factura["total"] == 1000.0
    assert factura["cae"]  # dev mock genera un CAE simulado


def test_complete_with_paid_deposit_covering_full_price_needs_no_medio_pago(
    admin_client: TestClient,
):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    deposit = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "1000.00"})
    deposit_id = deposit.json()["id"]
    client.post(f"/deposits/{deposit_id}/mark-paid", json={"medio_pago": "transferencia"})

    response = client.post(f"/appointments/{appointment_id}/complete")
    assert response.status_code == 200
    factura = response.json()["factura"]
    assert factura is not None
    assert factura["total"] == 1000.0


def test_complete_with_partial_deposit_requires_medio_pago_for_balance(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    deposit = client.post(f"/appointments/{appointment_id}/deposit", json={"amount": "400.00"})
    deposit_id = deposit.json()["id"]
    client.post(f"/deposits/{deposit_id}/mark-paid", json={"medio_pago": "mercadopago"})

    without_medio_pago = client.post(f"/appointments/{appointment_id}/complete")
    assert without_medio_pago.status_code == 422

    with_medio_pago = client.post(
        f"/appointments/{appointment_id}/complete", json={"medio_pago": "efectivo"},
    )
    assert with_medio_pago.status_code == 200
    assert with_medio_pago.json()["factura"]["total"] == 1000.0


def test_factura_type_is_a_for_responsable_inscripto_client(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client, client_data={
        "id": "client-1", "name": "Carlos",
        "cuit": "20111222339", "condicion_iva": "Responsable Inscripto",
    })
    response = client.post(
        f"/appointments/{appointment_id}/complete", json={"medio_pago": "efectivo"},
    )
    assert response.status_code == 200
    assert response.json()["factura"]["tipo"] == 1


def test_factura_type_is_b_for_consumidor_final_client(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client, client_data={
        "id": "client-1", "name": "Ana", "condicion_iva": "Consumidor Final",
    })
    response = client.post(
        f"/appointments/{appointment_id}/complete", json={"medio_pago": "efectivo"},
    )
    assert response.status_code == 200
    assert response.json()["factura"]["tipo"] == 6


def test_complete_twice_raises_invalid_transition_without_double_billing(admin_client: TestClient):
    client = admin_client
    appointment_id = _seeded_appointment(client)
    first = client.post(
        f"/appointments/{appointment_id}/complete", json={"medio_pago": "efectivo"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/appointments/{appointment_id}/complete", json={"medio_pago": "efectivo"},
    )
    assert second.status_code == 409


def test_config_arca_requires_admin(staff_client: TestClient):
    assert staff_client.get("/config/arca").status_code == 403

"""Con qué se puede cobrar un turno.

🔴 **Esta lista estaba hardcodeada en el frontend, y tenía un medio inventado.**
`Agenda.tsx` declaraba cuatro —efectivo, transferencia, **tarjeta** y
mercadopago— y ese `tarjeta` no existía en el vocabulario de la familia: **ni
siquiera en la caja que este producto crea por defecto**, que `services/billing.
py` arma con `list(db_caja.MEDIOS_PAGO_LABELS)`. O sea que el selector ofrecía un
medio que la instancia no tiene habilitado.

Peor: era la misma copia byte a byte que tenía MedLibra, así que dos productos
inventaron el mismo medio por separado, sin enterarse.
"""
from fastapi.testclient import TestClient
from libracore import medios_pago


def test_la_lista_sale_del_motor_y_no_de_este_producto(admin_client: TestClient):
    """🔴 No se comparan valores escritos a mano: se compara **contra el motor**.

    Una lista esperada escrita acá sería la copia número 29, y el test pasaría
    en verde el día que el motor cambie y este producto no."""
    respuesta = admin_client.get("/medios-pago")
    assert respuesta.status_code == 200, respuesta.text
    ids = [m["id"] for m in respuesta.json()]

    esperados = [m for m in medios_pago.ELEGIBLES if m != "cuenta_corriente"]
    assert ids == esperados
    # El control positivo: si el motor devolviera una lista vacía, la
    # comparación de arriba pasaría igual y no se habría medido nada.
    assert len(ids) >= 5, f"llegaron {len(ids)} medios: no se midió nada"


def test_no_se_ofrece_la_cuenta_corriente(admin_client: TestClient):
    """No es un medio de cobro: es la marca de que la operación se hizo a
    crédito. Quien completa un turno está cobrando; ofrecerla
    dejaría registrar un cobro que no cobra nada, y del otro lado sumaría deuda
    del cliente en vez de plata en la caja."""
    ids = [m["id"] for m in admin_client.get("/medios-pago").json()]
    assert "cuenta_corriente" not in ids
    assert "efectivo" in ids, "el control: la lista no vino vacía"


def test_la_tarjeta_viene_partida_en_debito_y_credito(admin_client: TestClient):
    """🔴 Es lo que ARCA declara: son dos condiciones de venta distintas en el
    comprobante, y **este producto emite comprobantes**. El `tarjeta` a secas
    que ofrecía el frontend obligaba a adivinar cuál era."""
    ids = [m["id"] for m in admin_client.get("/medios-pago").json()]
    assert "tarjeta_debito" in ids
    assert "tarjeta_credito" in ids
    # 🔴 Y la grafía vieja NO se ofrece: se lee —hay cobros ya registrados con
    # ese medio— pero no se escribe. Si se ofreciera, este producto nunca
    # migraría y el motor la rechazaría.
    assert "tarjeta" not in ids


def test_cada_medio_trae_su_etiqueta(admin_client: TestClient):
    """El selector muestra `label`, no el slug. Uno vacío dejaría una opción en
    blanco que igual se puede elegir."""
    for medio in admin_client.get("/medios-pago").json():
        assert medio["label"], medio


def test_el_mostrador_puede_leerla_sin_ser_admin(staff_client: TestClient):
    """🔴 **No va gateada por admin**, y es deliberado: la consume el selector
    del mostrador al completar un turno, y ahí no hay un admin. Con `admin_only`
    el diálogo de cobro se quedaría sin medios y el turno no se podría completar.

    Es una lista de constantes del motor: no expone nada de la instancia."""
    respuesta = staff_client.get("/medios-pago")
    assert respuesta.status_code == 200, respuesta.text
    assert len(respuesta.json()) >= 5

"""La factura registra contra qué ambiente de ARCA se emitió.

🔴 **El defecto que esto cierra.** Un comprobante emitido contra homologación
trae CAE y numeración del WSFE de homologación. Si cae en la misma tabla que los
reales y sin marcar, entra al Libro IVA del cliente y le rompe la correlatividad
— y ARCA lleva secuencias **independientes** por ambiente, así que también
desalinea la numeración.

Desde LibraCore `v1.71.0` `create_factura()` exige `ambiente` **por nombre**, sin
default: los dos defaults posibles mienten en direcciones opuestas y las dos
duelen. Marcar de producción un comprobante de prueba ensucia los libros; marcar
de prueba uno real lo **saca** del libro IVA en silencio, que es peor.

🔑 **Se parchea el numerador a propósito.** Con `ENV=development` —lo que fija
la suite— `get_next_numero_with_arca` devuelve el string `"_dev_mock_"` y **todo
sale `produccion`**: con eso, marcar bien y marcar siempre `produccion` dan
idéntico resultado y el defecto es invisible. Pasó exactamente eso al escribir
los tests equivalentes de Contalibra: la mutación sobrevivió.
"""
import pytest
from fastapi.testclient import TestClient
from libracore import arca_facturacion
from libracore.db import facturas as db_facturas


def _numerador(ambiente):
    """Un `get_next_numero_with_arca` que dice contra qué ambiente numeró."""
    async def _fake(punto_venta, tipo):
        if ambiente is None:
            return 1, None, None
        return 501, None, {"ambiente": ambiente, "cuit": "20111111119"}
    return _fake


@pytest.fixture
def _numero_de(monkeypatch):
    def _aplicar(ambiente):
        monkeypatch.setattr(arca_facturacion, "get_next_numero_with_arca",
                            _numerador(ambiente))
    return _aplicar


def _facturar(client: TestClient) -> dict:
    """Completa un turno con precio, que es el camino que emite."""
    from tests.test_billing import _seeded_appointment

    appointment_id = _seeded_appointment(client)
    r = client.post(f"/appointments/{appointment_id}/complete",
                    json={"medio_pago": "efectivo"})
    assert r.status_code == 200, r.text
    factura = r.json()["factura"]
    assert factura is not None, "no se emitió comprobante"
    return db_facturas.get_factura(factura["id"])


def test_en_homologacion_la_factura_queda_marcada_como_de_prueba(
        admin_client, _numero_de):
    """🔴 Sin esto el comprobante de prueba entra al Libro IVA del cliente."""
    _numero_de("homologacion")
    factura = _facturar(admin_client)
    assert factura["numero"] == 501, "no corrió el numerador parcheado"
    assert factura["ambiente"] == "homologacion"


def test_en_produccion_la_factura_queda_marcada_como_real(admin_client, _numero_de):
    """El control positivo: marcar **todo** como homologación pasaría el test de
    arriba — y sacaría del Libro IVA los comprobantes reales, que es el peor de
    los dos errores."""
    _numero_de("produccion")
    factura = _facturar(admin_client)
    assert factura["numero"] == 501
    assert factura["ambiente"] == "produccion"


def test_sin_arca_configurado_la_factura_es_real(admin_client, _numero_de):
    """Sin ARCA no hay CAE y el número es el de la propia instancia: ese
    comprobante **es** el real del cliente y tiene que entrar al Libro IVA."""
    _numero_de(None)
    assert _facturar(admin_client)["ambiente"] == "produccion"

"""La empresa ficticia de la demo pública (ADR-038 y ADR-061 de libracore).

En una demo (`DEMO_MODE=1`) el motor nunca muestra los datos de la empresa que
haya en `config.json` ni en `arca_config`: el emisor de un comprobante es esta
empresa y nada más. Es ficticia de punta a punta —CUIT con dígito verificador
válido y cuerpo `99999xxx`, que ARCA no asigna, correo en `.example`— y es el
mismo negocio que siembra `scripts/seed_demo.py` (la peluquería con dos
sucursales). Sin ella el comprobante de la demo sale con «Empresa Demo SRL», la
empresa genérica del motor.

Sin logo propio: el que sube la semilla vive en `DATA_DIR`, que en una demo no se
lee para el emisor (ADR-061).

Fuera de una demo, registrar no cambia nada.
"""
from libracore import config_manager

EMPRESA = {
    "empresa_nombre":             "Peluquería Estilo Norte SRL",
    "empresa_cuit":               "30-99999904-9",
    "empresa_direccion":          "Av. Demo 1234, San Miguel de Tucumán, Tucumán",
    "empresa_telefono":           "0381 400-0000",
    "empresa_email":              "administracion@estilonorte.example",
    "empresa_iibb":               "901-000000-4",
    "empresa_iva_condition":      "Responsable Inscripto",
    "empresa_inicio_actividades": "2018-03-01",
}


def registrar() -> None:
    """Idempotente: se puede llamar en cada arranque."""
    config_manager.usar_empresa_demo(EMPRESA)

"""Demo-only seeding endpoint.

Placeholder until the real CRUD of branches/resources/services/clients
lands (Fase 1, item 2 of the roadmap) — not meant to survive past that.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from libragenda import Branch, Client, Resource, Service
from libragenda.catalog_repository import SqlAlchemyCatalogRepository

from ..dependencies import get_catalog_repository

router = APIRouter()


class SeedRequest(BaseModel):
    resource_id: str
    resource_name: str
    service_id: str
    service_name: str
    client_id: str
    client_name: str
    duration_minutes: int = 30


@router.post("/demo/seed")
def seed(
    data: SeedRequest,
    catalog: SqlAlchemyCatalogRepository = Depends(get_catalog_repository),
):
    catalog.add_branch(Branch("demo-branch", "Sucursal demo"))
    catalog.add_client(Client(data.client_id, data.client_name))
    catalog.add_resource(Resource(data.resource_id, data.resource_name, "demo-branch"))
    catalog.add_service(
        Service(data.service_id, data.service_name, timedelta(minutes=data.duration_minutes))
    )
    return {"ok": True}

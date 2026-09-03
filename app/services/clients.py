"""Client: extiende el Client generico de LibraGenda con cuit/condicion_iva
para facturacion (mismo patron que Patient en MedLibra, ver DECISIONS.md).
El motor sigue sin saber nada de facturacion; la extension coordina el
Client de LibraGenda (identidad/agenda) con estos dos campos propios de
Gestiolibra en el borde de la API, dos tablas en vez de una sola.
"""
from datetime import UTC, datetime, timezone

from libragenda import Client
from libragenda.catalog_repository import SqlAlchemyCatalogRepository
from libragenda.sqlalchemy_repository import Base
from sqlalchemy import DateTime, ForeignKey, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker


class ClientBillingRow(Base):
    __tablename__ = "client_billing"

    id: Mapped[str] = mapped_column(ForeignKey("clients.id"), primary_key=True)
    cuit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    condicion_iva: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClientRepository:
    def __init__(
        self, catalog: SqlAlchemyCatalogRepository, session_factory: sessionmaker[Session],
    ) -> None:
        self.catalog = catalog
        self.session_factory = session_factory

    def create(
        self, id: str, name: str, phone: str | None, email: str | None, active: bool,
        cuit: str | None = None, condicion_iva: str | None = None,
    ) -> dict:
        client = Client(id, name, phone, email, active)
        self.catalog.add_client(client)  # raises IntegrityError on duplicate id
        with self.session_factory.begin() as session:
            session.add(ClientBillingRow(
                id=id, cuit=cuit, condicion_iva=condicion_iva,
                created_at=datetime.now(UTC),
            ))
        return self._to_out(client, cuit, condicion_iva)

    def count_active(self) -> int:
        return sum(1 for client in self.catalog.list_clients() if client.active)

    def count_created_between(self, date_from: datetime, date_to: datetime) -> int:
        """Cantidad de clientes dados de alta en el rango -- para el
        dashboard. Clientes preexistentes a esta feature no tienen
        `created_at` (columna agregada después, sin backfill) y quedan
        fuera de cualquier rango, nunca cuentan como "nuevos"."""
        with self.session_factory() as session:
            return session.scalar(
                select(func.count(ClientBillingRow.id)).where(
                    ClientBillingRow.created_at.is_not(None),
                    ClientBillingRow.created_at >= date_from,
                    ClientBillingRow.created_at <= date_to,
                )
            ) or 0

    def get(self, client_id: str) -> dict | None:
        client = self.catalog.get_client(client_id)
        if client is None:
            return None
        return self._to_out(client, *self._extension(client_id))

    def list(self) -> list[dict]:
        with self.session_factory() as session:
            extensions = {row.id: row for row in session.scalars(select(ClientBillingRow)).all()}
        return [
            self._to_out(
                client,
                extensions[client.id].cuit if client.id in extensions else None,
                extensions[client.id].condicion_iva if client.id in extensions else None,
            )
            for client in self.catalog.list_clients()
        ]

    def update(
        self, client_id: str, name: str, phone: str | None, email: str | None, active: bool,
        cuit: str | None = None, condicion_iva: str | None = None,
    ) -> dict:
        client = Client(client_id, name, phone, email, active)
        self.catalog.update_client(client_id, client)  # raises KeyError if missing
        with self.session_factory.begin() as session:
            row = session.get(ClientBillingRow, client_id)
            if row is None:
                row = ClientBillingRow(id=client_id)
                session.add(row)
            row.cuit, row.condicion_iva = cuit, condicion_iva
        return self._to_out(client, cuit, condicion_iva)

    def delete(self, client_id: str) -> None:
        # Borrar primero la extension (ClientBillingRow.id tiene FK a
        # clients.id): borrar el Client antes violaria esa FK en Postgres
        # real -- mismo bug ya encontrado y corregido en PatientRepository/
        # BranchRepository de esta familia.
        with self.session_factory.begin() as session:
            row = session.get(ClientBillingRow, client_id)
            if row is not None:
                session.delete(row)
        self.catalog.delete_client(client_id)  # raises KeyError/IntegrityError

    def _extension(self, client_id: str) -> tuple[str | None, str | None]:
        with self.session_factory() as session:
            row = session.get(ClientBillingRow, client_id)
            return (row.cuit, row.condicion_iva) if row else (None, None)

    @staticmethod
    def _to_out(client: Client, cuit: str | None, condicion_iva: str | None) -> dict:
        return {
            "id": client.id, "name": client.name, "phone": client.phone,
            "email": client.email, "active": client.active,
            "cuit": cuit, "condicion_iva": condicion_iva,
        }

"""Small idempotent primitives used later by the synchronization layer."""

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from partner_reports.contracts.ingestion import AdvboxCustomerInput
from partner_reports.persistence.models import Customer


def upsert_customer(session: Session, item: AdvboxCustomerInput) -> uuid.UUID:
    """Insert or update one normalized customer using the stable Advbox ID."""

    statement = (
        insert(Customer)
        .values(
            id=uuid.uuid4(),
            advbox_id=item.external_id,
            name=item.name,
            identification=item.identification,
            origin=item.origin,
            source_created_at=item.source_created_at,
            status="active",
        )
        .on_conflict_do_update(
            index_elements=[Customer.advbox_id],
            set_={
                "name": item.name,
                "identification": item.identification,
                "origin": item.origin,
                "source_created_at": item.source_created_at,
                "status": "active",
                "deleted_at": None,
            },
        )
        .returning(Customer.id)
    )
    return session.execute(statement).scalar_one()

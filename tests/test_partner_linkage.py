"""Synthetic tests for deterministic partner-to-portfolio linkage."""

from datetime import date

from partner_reports.domain.partner_linkage import (
    AdvboxEntityType,
    LawsuitReference,
    MappingStatus,
    PartnerMapping,
    validate_partner_linkage,
)


def _mapping(
    partner: str,
    entity_type: AdvboxEntityType,
    entity_id: str,
    *,
    valid_to: date | None = None,
    status: MappingStatus = MappingStatus.ACTIVE,
) -> PartnerMapping:
    return PartnerMapping(
        partner_external_id=partner,
        entity_type=entity_type,
        entity_id=entity_id,
        valid_from=date(2026, 1, 1),
        valid_to=valid_to,
        status=status,
    )


def test_validator_classifies_every_record_and_rejects_ambiguity() -> None:
    result = validate_partner_linkage(
        customer_ids={"customer-a", "customer-b", "customer-c"},
        lawsuits=(
            LawsuitReference("lawsuit-a", ("customer-a",)),
            LawsuitReference("lawsuit-b", ("customer-b",)),
            LawsuitReference("lawsuit-c", ("customer-c",)),
        ),
        mappings=(
            _mapping("partner-a", AdvboxEntityType.CUSTOMER, "customer-a"),
            _mapping("partner-a", AdvboxEntityType.LAWSUIT, "lawsuit-a"),
            _mapping("partner-a", AdvboxEntityType.CUSTOMER, "customer-b"),
            _mapping("partner-b", AdvboxEntityType.LAWSUIT, "lawsuit-b"),
        ),
        reference_date=date(2026, 9, 15),
    )

    assert result.customers.total == 3
    assert result.customers.linked == 2
    assert result.customers.unlinked == 1
    assert result.customers.multiple == 0
    assert result.lawsuits.total == 3
    assert result.lawsuits.linked == 1
    assert result.lawsuits.unlinked == 1
    assert result.lawsuits.multiple == 1
    assert result.has_ambiguity


def test_inactive_and_expired_mappings_do_not_link() -> None:
    result = validate_partner_linkage(
        customer_ids={"customer-a"},
        lawsuits=(LawsuitReference("lawsuit-a", ("customer-a",)),),
        mappings=(
            _mapping(
                "partner-a",
                AdvboxEntityType.CUSTOMER,
                "customer-a",
                valid_to=date(2026, 6, 1),
            ),
            _mapping(
                "partner-a",
                AdvboxEntityType.LAWSUIT,
                "lawsuit-a",
                status=MappingStatus.INACTIVE,
            ),
        ),
        reference_date=date(2026, 9, 15),
    )

    assert result.customers.unlinked == 1
    assert result.lawsuits.unlinked == 1
    assert not result.has_ambiguity


def test_nonexistent_mapping_references_are_counted_without_ids_in_result() -> None:
    missing_identifier = "synthetic-missing-entity"
    result = validate_partner_linkage(
        customer_ids=set(),
        lawsuits=(),
        mappings=(_mapping("partner-a", AdvboxEntityType.CUSTOMER, missing_identifier),),
        reference_date=date(2026, 9, 15),
    )

    assert result.nonexistent_references == 1
    assert missing_identifier not in repr(result)


def test_mapping_repr_hides_partner_and_entity_identifiers() -> None:
    mapping = _mapping(
        "synthetic-private-partner-id",
        AdvboxEntityType.LAWSUIT,
        "synthetic-private-lawsuit-id",
    )

    representation = repr(mapping)

    assert "synthetic-private-partner-id" not in representation
    assert "synthetic-private-lawsuit-id" not in representation

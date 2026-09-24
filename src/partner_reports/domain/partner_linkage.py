"""Deterministic partner linkage rules with count-only validation output."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class AdvboxEntityType(StrEnum):
    """Advbox entities that may receive an administrated partner mapping."""

    CUSTOMER = "customer"
    LAWSUIT = "lawsuit"


class MappingStatus(StrEnum):
    """Lifecycle states supported by the future mapping repository."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


@dataclass(frozen=True)
class PartnerMapping:
    """A value-free-in-logs representation of one effective mapping."""

    partner_external_id: str = field(repr=False)
    entity_type: AdvboxEntityType
    entity_id: str = field(repr=False)
    valid_from: date
    valid_to: date | None = None
    status: MappingStatus = MappingStatus.ACTIVE

    def is_effective_on(self, reference_date: date) -> bool:
        """Return whether the mapping participates in linkage on the given date."""

        if self.status is not MappingStatus.ACTIVE:
            return False
        if self.valid_from > reference_date:
            return False
        return self.valid_to is None or reference_date <= self.valid_to


@dataclass(frozen=True)
class LawsuitReference:
    """Opaque process/customer relation used only while validating counts."""

    lawsuit_id: str = field(repr=False)
    customer_ids: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class LinkageCounts:
    """Safe aggregate that can be logged and persisted."""

    total: int
    linked: int
    unlinked: int
    multiple: int


@dataclass(frozen=True)
class LinkageValidationResult:
    """Count-only result for the complete observed portfolio."""

    customers: LinkageCounts
    lawsuits: LinkageCounts
    nonexistent_references: int

    @property
    def has_ambiguity(self) -> bool:
        return self.customers.multiple > 0 or self.lawsuits.multiple > 0


def _classify_partner_sets(partner_sets: list[set[str]]) -> LinkageCounts:
    linked = sum(len(partners) == 1 for partners in partner_sets)
    unlinked = sum(not partners for partners in partner_sets)
    multiple = sum(len(partners) > 1 for partners in partner_sets)
    return LinkageCounts(
        total=len(partner_sets),
        linked=linked,
        unlinked=unlinked,
        multiple=multiple,
    )


def validate_partner_linkage(
    *,
    customer_ids: set[str],
    lawsuits: tuple[LawsuitReference, ...],
    mappings: tuple[PartnerMapping, ...],
    reference_date: date,
) -> LinkageValidationResult:
    """Classify every entity exactly once without returning any identifying value."""

    lawsuit_ids = {lawsuit.lawsuit_id for lawsuit in lawsuits}
    known_entities = {
        AdvboxEntityType.CUSTOMER: customer_ids,
        AdvboxEntityType.LAWSUIT: lawsuit_ids,
    }
    nonexistent_references = sum(
        mapping.entity_id not in known_entities[mapping.entity_type] for mapping in mappings
    )

    active_index: dict[tuple[AdvboxEntityType, str], set[str]] = {}
    for mapping in mappings:
        if not mapping.is_effective_on(reference_date):
            continue
        key = (mapping.entity_type, mapping.entity_id)
        active_index.setdefault(key, set()).add(mapping.partner_external_id)

    customer_partner_sets = [
        active_index.get((AdvboxEntityType.CUSTOMER, customer_id), set())
        for customer_id in customer_ids
    ]
    lawsuit_partner_sets: list[set[str]] = []
    for lawsuit in lawsuits:
        partners = set(active_index.get((AdvboxEntityType.LAWSUIT, lawsuit.lawsuit_id), set()))
        for customer_id in lawsuit.customer_ids:
            partners.update(active_index.get((AdvboxEntityType.CUSTOMER, customer_id), set()))
        lawsuit_partner_sets.append(partners)

    return LinkageValidationResult(
        customers=_classify_partner_sets(customer_partner_sets),
        lawsuits=_classify_partner_sets(lawsuit_partner_sets),
        nonexistent_references=nonexistent_references,
    )

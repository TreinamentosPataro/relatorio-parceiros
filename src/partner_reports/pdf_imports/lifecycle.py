"""Explicit, testable lifecycle for PDF import batches."""

from enum import StrEnum


class PdfBatchState(StrEnum):
    UPLOADED = "uploaded"
    QUARANTINED = "quarantined"
    PARSING = "parsing"
    PARSED = "parsed"
    RECONCILING = "reconciling"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"


ALLOWED_TRANSITIONS: dict[PdfBatchState, frozenset[PdfBatchState]] = {
    PdfBatchState.UPLOADED: frozenset({PdfBatchState.QUARANTINED}),
    PdfBatchState.QUARANTINED: frozenset(
        {PdfBatchState.PARSING, PdfBatchState.REJECTED, PdfBatchState.FAILED}
    ),
    PdfBatchState.PARSING: frozenset(
        {
            PdfBatchState.PARSED,
            PdfBatchState.NEEDS_REVIEW,
            PdfBatchState.REJECTED,
            PdfBatchState.FAILED,
        }
    ),
    PdfBatchState.PARSED: frozenset({PdfBatchState.RECONCILING, PdfBatchState.NEEDS_REVIEW}),
    PdfBatchState.RECONCILING: frozenset(
        {PdfBatchState.APPROVED, PdfBatchState.NEEDS_REVIEW, PdfBatchState.FAILED}
    ),
    PdfBatchState.NEEDS_REVIEW: frozenset(
        {
            PdfBatchState.RECONCILING,
            PdfBatchState.APPROVED,
            PdfBatchState.REJECTED,
            PdfBatchState.SUPERSEDED,
        }
    ),
    PdfBatchState.FAILED: frozenset({PdfBatchState.QUARANTINED}),
    PdfBatchState.APPROVED: frozenset({PdfBatchState.SUPERSEDED}),
    PdfBatchState.REJECTED: frozenset(),
    PdfBatchState.SUPERSEDED: frozenset(),
}


def require_transition(current: PdfBatchState | str, target: PdfBatchState | str) -> None:
    """Reject lifecycle changes outside the contract."""

    try:
        current_state = PdfBatchState(current)
        target_state = PdfBatchState(target)
    except ValueError as exc:
        raise ValueError("estado de importação inválido") from exc
    if target_state not in ALLOWED_TRANSITIONS[current_state]:
        raise ValueError("transição de importação inválida")

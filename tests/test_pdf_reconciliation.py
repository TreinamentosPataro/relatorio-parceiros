"""Synthetic-only exact matching and official GET transport tests for PDF-3."""

import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from partner_reports.integrations.advbox.client import (
    AdvboxClient,
    AdvboxSourceChanged,
    AdvboxTransportError,
    AdvboxUnexpectedResponse,
    ConservativeRateLimiter,
)
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.pdf_imports.parser import ManifestItem
from partner_reports.pdf_imports.reconciliation import (
    SNAPSHOT_PAGE_SIZE,
    ApiCandidate,
    ApiSnapshot,
    MatchMethod,
    MatchStatus,
    RelevantKeys,
    ScanCheckpoint,
    _snapshot_digest,
    advance_scan,
    collect_official_enrichment_coverage,
    collect_verified_snapshot,
    reconcile_items,
    summarize,
)


def _item(number: str | None, folder: str | None, *flags: str) -> ManifestItem:
    return ManifestItem(uuid.uuid4(), 1, number, folder, 1, 1, flags)


def _snapshot(*rows: tuple[int, str | None, str | None]) -> ApiSnapshot:
    candidates = tuple(
        ApiCandidate(identifier, number, folder, f"digest-{identifier}")
        for identifier, number, folder in rows
    )
    return ApiSnapshot(_snapshot_digest(candidates), len(candidates), datetime.now(UTC), candidates)


def _settings() -> AdvboxAuditSettings:
    return AdvboxAuditSettings(  # type: ignore[call-arg]
        advbox_api_token=SecretStr("synthetic-token"), advbox_audit_max_retries=2
    )


def _api_row(
    identifier: int,
    *,
    number: str | None = None,
    folder: str | None = None,
    name: str = "Synthetic Person",
) -> dict:
    return {
        "id": identifier,
        "process_number": number,
        "folder": folder,
        "customers": [{"customer_id": identifier, "name": name}],
        "responsible": name,
    }


def test_exact_number_folder_and_name_never_matches() -> None:
    number = "12345678920261234567"
    snapshot = _snapshot((1, number, "PASTA-01"), (2, None, "PASTA-02"))
    items = (
        _item("1234567-89.2026.1.23.4567", "PASTA-01"),
        _item(None, "PASTA-02"),
        _item(None, "Synthetic Person"),
        _item("11111111120261234567", "PASTA-02"),
    )
    results = reconcile_items(items, snapshot)
    assert [result.status for result in results] == [
        MatchStatus.MATCHED,
        MatchStatus.MATCHED,
        MatchStatus.UNMATCHED,
        MatchStatus.UNMATCHED,
    ]
    assert [result.method for result in results[:2]] == [
        MatchMethod.PROCESS_NUMBER_EXACT,
        MatchMethod.FOLDER_EXACT_UNIQUE,
    ]
    assert results[3].matched_advbox_id is None  # Number present forbids folder fallback.
    assert summarize(results).total == len(items)


def test_ambiguity_conflict_duplicates_and_invalid_identifiers_never_link() -> None:
    number = "12345678920261234567"
    snapshot = _snapshot(
        (1, number, "PASTA-01"), (2, number, "PASTA-02"), (3, None, "PASTA-X"), (4, None, "PASTA-X")
    )
    items = (
        _item(number, "PASTA-01"),
        _item(None, "PASTA-X"),
        _item(None, "PASTA-Y", "invalid_identifier"),
        _item(None, None, "missing_identifier"),
    )
    statuses = [result.status for result in reconcile_items(items, snapshot)]
    assert statuses == [
        MatchStatus.AMBIGUOUS,
        MatchStatus.AMBIGUOUS,
        MatchStatus.INVALID_IDENTIFIER,
        MatchStatus.INVALID_IDENTIFIER,
    ]
    assert all(result.matched_advbox_id is None for result in reconcile_items(items, snapshot))

    unique = _snapshot((1, number, "PASTA-01"))
    conflict = reconcile_items((_item(number, "OTHER"),), unique)
    assert conflict[0].status is MatchStatus.AMBIGUOUS
    duplicate = reconcile_items((_item(number, "PASTA-01"), _item(number, "PASTA-01")), unique)
    assert all(result.status is MatchStatus.DUPLICATE_SOURCE for result in duplicate)
    assert all(result.matched_advbox_id is None for result in duplicate)


def test_two_pass_snapshot_retries_and_only_gets() -> None:
    rows = [_api_row(1, number="1234567-89.2026.1.23.4567", folder="PASTA-01")]
    seen: list[str] = []
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        if len(seen) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        if len(seen) == 2:
            raise httpx.ReadTimeout("synthetic timeout")
        return httpx.Response(
            200,
            json={
                "data": rows,
                "totalCount": 1,
                "limit": int(request.url.params["limit"]),
                "offset": 0,
            },
        )

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    async def run() -> ApiSnapshot:
        client = AdvboxClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            sleep=fake_sleep,
            random_value=lambda: 0,
            limiter=ConservativeRateLimiter(20, sleep=fake_sleep, clock=lambda: 0),
        )
        try:
            return await collect_verified_snapshot(client)
        finally:
            await client.aclose()

    snapshot = asyncio.run(run())
    assert snapshot.total == 1
    assert len(seen) == 4  # Two failures, first pass, verification pass.
    assert seen == ["GET"] * 4
    assert 2 in delays


def test_changed_origin_blocks_snapshot_and_resume_uses_checkpoint() -> None:
    rows = [
        _api_row(index, folder=f"PASTA-{index:03d}") for index in range(1, SNAPSHOT_PAGE_SIZE + 2)
    ]
    calls: list[int] = []
    failed = [False]

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        calls.append(offset)
        if offset == SNAPSHOT_PAGE_SIZE and not failed[0]:
            failed[0] = True
            raise httpx.ReadTimeout("synthetic timeout")
        return httpx.Response(
            200,
            json={
                "data": rows[offset : offset + SNAPSHOT_PAGE_SIZE],
                "totalCount": len(rows),
                "limit": SNAPSHOT_PAGE_SIZE,
                "offset": offset,
            },
        )

    async def run() -> ApiSnapshot:
        settings = _settings().model_copy(update={"advbox_audit_max_retries": 0})
        client = AdvboxClient(
            settings,
            transport=httpx.MockTransport(handler),
            limiter=ConservativeRateLimiter(20, sleep=lambda _: asyncio.sleep(0), clock=lambda: 0),
        )
        try:
            checkpoint = await advance_scan(client, ScanCheckpoint())
            with pytest.raises(AdvboxTransportError):
                await advance_scan(client, checkpoint)
            assert checkpoint.next_offset == SNAPSHOT_PAGE_SIZE
            return await collect_verified_snapshot(client, checkpoint)
        finally:
            await client.aclose()

    snapshot = asyncio.run(run())
    assert snapshot.total == SNAPSHOT_PAGE_SIZE + 1
    assert calls.count(0) == 2  # First page checkpoint, then full verification pass.

    changing = [0]

    def changed_handler(request: httpx.Request) -> httpx.Response:
        changing[0] += 1
        folder = "PASTA-01" if changing[0] == 1 else "PASTA-02"
        return httpx.Response(
            200,
            json={
                "data": [_api_row(1, folder=folder)],
                "totalCount": 1,
                "limit": int(request.url.params["limit"]),
                "offset": 0,
            },
        )

    async def reject() -> None:
        client = AdvboxClient(_settings(), transport=httpx.MockTransport(changed_handler))
        try:
            with pytest.raises(AdvboxUnexpectedResponse, match="origem mudou"):
                await collect_verified_snapshot(client)
        finally:
            await client.aclose()

    asyncio.run(reject())


def test_official_enrichment_returns_only_related_counts() -> None:
    candidate = ApiCandidate(1, "12345678920261234567", "PASTA-01", "synthetic-digest", (3,))
    snapshot = ApiSnapshot(_snapshot_digest((candidate,)), 1, datetime.now(UTC), (candidate,))
    results = reconcile_items((_item("12345678920261234567", "PASTA-01"),), snapshot)
    resources = {
        "customers": [{"id": 3, "name": "Synthetic Person"}],
        "transactions": [
            {
                "id": 5,
                "lawsuit_id": 1,
                "amount": 10,
                "is_internal": True,
                "description": "discarded",
            }
        ],
        "last_movements": [
            {"lawsuit_id": 1, "date": "2026-09-01", "title": "Discarded synthetic narrative"}
        ],
    }
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        resource = request.url.path.rsplit("/", 1)[-1]
        paths.append(resource)
        rows = resources[resource]
        return httpx.Response(
            200,
            json={
                "data": rows,
                "totalCount": len(rows),
                "limit": int(request.url.params["limit"]),
                "offset": 0,
            },
        )

    async def execute():
        client = AdvboxClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            limiter=ConservativeRateLimiter(20, sleep=lambda _: asyncio.sleep(0), clock=lambda: 0),
        )
        try:
            return await collect_official_enrichment_coverage(client, snapshot, results)
        finally:
            await client.aclose()

    coverage = asyncio.run(execute())
    assert coverage.referenced_customers == coverage.customers_found == 1
    assert coverage.transactions_found == coverage.last_movements_found == 1
    assert paths == ["customers", "transactions", "last_movements"]
    assert "Discarded" not in repr(coverage)


def test_matching_person_name_in_api_never_becomes_a_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [_api_row(1, name="Synthetic Person")],
                "totalCount": 1,
                "limit": int(request.url.params["limit"]),
                "offset": 0,
            },
        )

    async def execute() -> ApiSnapshot:
        client = AdvboxClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            limiter=ConservativeRateLimiter(20, sleep=lambda _: asyncio.sleep(0), clock=lambda: 0),
        )
        try:
            return await collect_verified_snapshot(client)
        finally:
            await client.aclose()

    snapshot = asyncio.run(execute())
    assert (
        reconcile_items((_item(None, "Synthetic Person"),), snapshot)[0].status
        is MatchStatus.UNMATCHED
    )


def test_snapshot_item_limit_fails_closed(monkeypatch) -> None:
    import partner_reports.pdf_imports.reconciliation as reconciliation

    monkeypatch.setattr(reconciliation, "MAX_SNAPSHOT_ITEMS", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [_api_row(1, folder="PASTA-01")],
                "totalCount": 1,
                "limit": int(request.url.params["limit"]),
                "offset": 0,
            },
        )

    async def execute() -> None:
        client = AdvboxClient(_settings(), transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(AdvboxUnexpectedResponse, match="limite técnico"):
                await advance_scan(client, ScanCheckpoint())
        finally:
            await client.aclose()

    asyncio.run(execute())


def test_only_manifest_lawsuits_must_agree_between_reads() -> None:
    number = "12345678920261234567"
    keys = RelevantKeys.from_manifest((_item(number, "PASTA-01"),))
    reads = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        reads[0] += 1
        second = reads[0] > 1
        rows = [
            _api_row(1, number="1234567-89.2026.1.23.4567", folder="PASTA-01"),
            # Another lawsuit edited (and one created) by the office between reads.
            _api_row(2, folder="OUTRA-PASTA-EDITADA" if second else "OUTRA-PASTA"),
            *([_api_row(3, folder="NOVA")] if second else []),
        ]
        return httpx.Response(
            200,
            json={
                "data": rows,
                "totalCount": len(rows),
                "limit": int(request.url.params["limit"]),
                "offset": 0,
            },
        )

    async def read(relevant: RelevantKeys | None) -> ApiSnapshot:
        reads[0] = 0
        client = AdvboxClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            limiter=ConservativeRateLimiter(20, sleep=lambda _: asyncio.sleep(0), clock=lambda: 0),
        )
        try:
            return await collect_verified_snapshot(client, relevant=relevant)
        finally:
            await client.aclose()

    snapshot = asyncio.run(read(keys))
    assert snapshot.total == 2
    with pytest.raises(AdvboxSourceChanged):
        asyncio.run(read(None))
    with pytest.raises(AdvboxSourceChanged):
        # The manifest lawsuit itself changed: the read is refused.
        asyncio.run(read(RelevantKeys.from_manifest((_item(None, "OUTRA-PASTA"),))))

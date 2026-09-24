"""Synthetic read-only transport and global throttle tests."""

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from partner_reports.integrations.advbox.client import (
    AdvboxClient,
    AdvboxTransportError,
    ConservativeRateLimiter,
)
from partner_reports.integrations.advbox.config import AdvboxAuditSettings


def _settings() -> AdvboxAuditSettings:
    return AdvboxAuditSettings(  # type: ignore[call-arg]
        advbox_api_token=SecretStr("synthetic-token"),
        advbox_audit_max_retries=1,
    )


def test_429_retry_after_and_timeout_recover_without_mutable_calls() -> None:
    seen: list[str] = []
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        if len(seen) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        if len(seen) == 2:
            raise httpx.ReadTimeout("synthetic timeout")
        return httpx.Response(200, json={"data": [], "totalCount": 0, "limit": 100, "offset": 0})

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def execute() -> None:
        client = AdvboxClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            sleep=fake_sleep,
            random_value=lambda: 0,
            limiter=ConservativeRateLimiter(20, sleep=fake_sleep, clock=lambda: 0),
        )
        try:
            # One retry is intentionally exhausted after the synthetic timeout.
            with pytest.raises(AdvboxTransportError):
                await client.list_page("customers", limit=100, offset=0)
        finally:
            await client.aclose()

    asyncio.run(execute())
    assert seen == ["GET", "GET"]
    assert 7 in delays


def test_timeout_retry_and_rate_limit_shared_between_resources() -> None:
    clock = [0.0]
    sleeps: list[float] = []
    requests: list[tuple[str, float]] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock[0] += delay

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, clock[0]))
        if len(requests) == 1:
            raise httpx.ReadTimeout("synthetic timeout")
        return httpx.Response(200, json={"data": [], "totalCount": 0, "limit": 100, "offset": 0})

    async def execute() -> None:
        client = AdvboxClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            sleep=fake_sleep,
            random_value=lambda: 0,
            limiter=ConservativeRateLimiter(20, sleep=fake_sleep, clock=lambda: clock[0]),
        )
        try:
            await client.list_page("customers", limit=100, offset=0)
            await client.list_page("lawsuits", limit=100, offset=0)
        finally:
            await client.aclose()

    asyncio.run(execute())
    assert len(requests) == 3
    assert requests[1][1] - requests[0][1] >= 3
    assert requests[2][1] - requests[1][1] >= 3
    assert all(path.endswith(("/customers", "/lawsuits")) for path, _ in requests)

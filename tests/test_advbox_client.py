"""Synthetic contract tests for the GET-only Advbox audit client."""

import asyncio
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from partner_reports.integrations.advbox.client import (
    AdvboxAuditClient,
    AdvboxAuthenticationError,
    AdvboxForbiddenError,
    AdvboxNotFoundError,
    AdvboxRateLimitError,
    AdvboxServerError,
    MutableOperationBlocked,
)
from partner_reports.integrations.advbox.config import AdvboxAuditSettings


class NoopLimiter:
    async def wait(self) -> None:
        return None


def _settings(**overrides: object) -> AdvboxAuditSettings:
    values: dict[str, object] = {
        "advbox_api_token": SecretStr("synthetic-secret-token"),
        "advbox_audit_max_retries": 1,
    }
    values.update(overrides)
    return AdvboxAuditSettings(**values)  # type: ignore[arg-type]


def _run_request(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[httpx.Request, object]:
    captured: list[httpx.Request] = []

    def capturing_handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    async def execute() -> object:
        client = AdvboxAuditClient(
            _settings(),
            transport=httpx.MockTransport(capturing_handler),
            limiter=NoopLimiter(),  # type: ignore[arg-type]
            sleep=_no_sleep,
            random_value=lambda: 0,
        )
        try:
            return await client.get("/customers", params={"limit": 1})
        finally:
            await client.aclose()

    result = asyncio.run(execute())
    return captured[0], result


async def _no_sleep(_: float) -> None:
    return None


def test_client_sends_bearer_auth_and_get_only() -> None:
    request, result = _run_request(lambda _: httpx.Response(200, json={"data": []}))

    assert request.method == "GET"
    assert request.headers["Authorization"] == "Bearer synthetic-secret-token"
    assert result.status_code == 200


def test_non_get_and_absolute_url_are_blocked_before_transport() -> None:
    AdvboxAuditClient.assert_read_only("GET")

    with pytest.raises(MutableOperationBlocked):
        AdvboxAuditClient.assert_read_only("DELETE")

    async def execute() -> None:
        client = AdvboxAuditClient(
            _settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
            limiter=NoopLimiter(),  # type: ignore[arg-type]
        )
        try:
            with pytest.raises(MutableOperationBlocked):
                await client.get("https://untrusted.invalid/customers")
        finally:
            await client.aclose()

    asyncio.run(execute())


@pytest.mark.parametrize(
    ("status", "expected_exception"),
    [
        (401, AdvboxAuthenticationError),
        (403, AdvboxForbiddenError),
        (404, AdvboxNotFoundError),
    ],
)
def test_explicit_non_retryable_statuses(status: int, expected_exception: type[Exception]) -> None:
    async def execute() -> None:
        client = AdvboxAuditClient(
            _settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(status)),
            limiter=NoopLimiter(),  # type: ignore[arg-type]
        )
        try:
            with pytest.raises(expected_exception):
                await client.get("/settings")
        finally:
            await client.aclose()

    asyncio.run(execute())


@pytest.mark.parametrize(
    ("status", "expected_exception"),
    [(429, AdvboxRateLimitError), (503, AdvboxServerError)],
)
def test_retryable_statuses_are_bounded(status: int, expected_exception: type[Exception]) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, headers={"Retry-After": "0"})

    async def execute() -> None:
        client = AdvboxAuditClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            limiter=NoopLimiter(),  # type: ignore[arg-type]
            sleep=_no_sleep,
            random_value=lambda: 0,
        )
        try:
            with pytest.raises(expected_exception):
                await client.get("/transactions")
        finally:
            await client.aclose()

    asyncio.run(execute())
    assert calls == 2


def test_retry_can_recover_without_exposing_body() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="synthetic-sensitive-error-body")
        return httpx.Response(200, json={"data": []})

    _, result = _run_request(handler)

    assert result.status_code == 200
    assert "synthetic-sensitive-error-body" not in repr(result)


def test_transport_metrics_count_retries_without_response_content() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        if calls == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": []})

    async def execute():
        client = AdvboxAuditClient(
            _settings(advbox_audit_max_retries=2),
            transport=httpx.MockTransport(handler),
            limiter=NoopLimiter(),  # type: ignore[arg-type]
            sleep=_no_sleep,
            random_value=lambda: 0,
        )
        try:
            await client.get("/customers")
            return client.metrics
        finally:
            await client.aclose()

    metrics = asyncio.run(execute())
    assert metrics.requests == 3
    assert metrics.http_429 == 1
    assert metrics.http_5xx == 1
    assert metrics.transport_errors == 0

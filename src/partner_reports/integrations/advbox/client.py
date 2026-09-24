"""Conservative GET-only transport shared by audit and synchronization."""

import asyncio
import math
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from partner_reports.integrations.advbox.config import AdvboxAuditSettings


class AdvboxAuditError(RuntimeError):
    """Base exception whose text is safe to show without response data."""


class MutableOperationBlocked(AdvboxAuditError):
    """Raised before any non-GET request can be sent."""


class AdvboxAuthenticationError(AdvboxAuditError):
    """Authentication failed or redirected to an interactive login."""


class AdvboxForbiddenError(AdvboxAuditError):
    """The credential lacks access to the requested resource."""


class AdvboxNotFoundError(AdvboxAuditError):
    """The documented resource was not found."""


class AdvboxRateLimitError(AdvboxAuditError):
    """The API kept returning HTTP 429 after bounded retries."""


class AdvboxServerError(AdvboxAuditError):
    """The API kept returning a server error after bounded retries."""


class AdvboxTransportError(AdvboxAuditError):
    """The network failed after bounded retries."""


class AdvboxUnexpectedResponse(AdvboxAuditError):
    """The API response did not match the safe read-only contract."""


@dataclass(frozen=True)
class SafeHttpResult:
    """A successful response plus timing; callers must immediately sanitize payload."""

    status_code: int
    duration_ms: int
    payload: Any = field(repr=False)


@dataclass
class RequestMetrics:
    """Count-only transport evidence safe for homologation output."""

    requests: int = 0
    http_429: int = 0
    http_5xx: int = 0
    transport_errors: int = 0
    response_duration_ms: int = 0


class ConservativeRateLimiter:
    """Space requests so this process never exceeds the configured audit ceiling."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 1 <= requests_per_minute <= 20:
            raise ValueError("A auditoria deve operar entre 1 e 20 GET/min")
        self._minimum_interval = 60.0 / requests_per_minute
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None

    async def wait(self) -> None:
        """Wait until one request slot is available."""

        now = self._clock()
        if self._last_request_at is not None:
            remaining = self._minimum_interval - (now - self._last_request_at)
            if remaining > 0:
                await self._sleep(remaining)
        self._last_request_at = self._clock()


class AdvboxAuditClient:
    """Small GET-only client that never logs headers, response bodies, or URLs with IDs."""

    def __init__(
        self,
        settings: AdvboxAuditSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_value: Callable[[], float] = random.random,
        limiter: ConservativeRateLimiter | None = None,
    ) -> None:
        self._max_retries = settings.advbox_audit_max_retries
        self._sleep = sleep
        self._random_value = random_value
        self._limiter = limiter or ConservativeRateLimiter(
            settings.advbox_audit_requests_per_minute,
            sleep=sleep,
        )
        self.metrics = RequestMetrics()
        timeout = httpx.Timeout(settings.advbox_audit_timeout_seconds)
        self._http = httpx.AsyncClient(
            base_url=str(settings.advbox_api_base_url).rstrip("/") + "/",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {settings.advbox_api_token.get_secret_value()}",
                "User-Agent": "partner-reports-read-only-auditor/0.1",
            },
            follow_redirects=False,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> "AdvboxAuditClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Release the connection pool."""

        await self._http.aclose()

    @staticmethod
    def assert_read_only(method: str) -> None:
        """Fail closed before constructing any mutable HTTP request."""

        if method.upper() != "GET":
            raise MutableOperationBlocked("auditoria bloqueou método HTTP diferente de GET")

    @staticmethod
    def _validate_endpoint(endpoint: str) -> str:
        parsed = urlsplit(endpoint)
        if not endpoint.startswith("/") or parsed.scheme or parsed.netloc:
            raise MutableOperationBlocked("auditoria aceita apenas caminhos relativos conhecidos")
        return endpoint.lstrip("/")

    async def get(
        self,
        endpoint: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> SafeHttpResult:
        """Perform a bounded GET and return content only for immediate sanitization."""

        self.assert_read_only("GET")
        safe_endpoint = self._validate_endpoint(endpoint)

        for attempt in range(self._max_retries + 1):
            await self._limiter.wait()
            started_at = time.perf_counter()
            self.metrics.requests += 1
            try:
                response = await self._http.get(safe_endpoint, params=params)
            except (httpx.TimeoutException, httpx.NetworkError):
                self.metrics.transport_errors += 1
                if attempt >= self._max_retries:
                    raise AdvboxTransportError("falha de rede após retentativas") from None
                await self._backoff(attempt, retry_after=None)
                continue

            duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
            self.metrics.response_duration_ms += duration_ms
            status = response.status_code
            if status == 429:
                self.metrics.http_429 += 1
            elif 500 <= status < 600:
                self.metrics.http_5xx += 1

            if status == 204:
                return SafeHttpResult(status, duration_ms, None)
            if 200 <= status < 300:
                try:
                    payload = response.json(parse_float=Decimal)
                except ValueError:
                    raise AdvboxUnexpectedResponse(
                        f"HTTP {status}: resposta não contém JSON válido"
                    ) from None
                return SafeHttpResult(status, duration_ms, payload)
            if status in {301, 302, 303, 307, 308, 401}:
                raise AdvboxAuthenticationError(f"HTTP {status}: autenticação não confirmada")
            if status == 403:
                raise AdvboxForbiddenError("HTTP 403: acesso negado")
            if status == 404:
                raise AdvboxNotFoundError("HTTP 404: recurso não encontrado")
            if status == 429:
                if attempt >= self._max_retries:
                    raise AdvboxRateLimitError("HTTP 429 após retentativas")
                await self._backoff(attempt, retry_after=response.headers.get("Retry-After"))
                continue
            if 500 <= status < 600:
                if attempt >= self._max_retries:
                    raise AdvboxServerError(f"HTTP {status} após retentativas")
                await self._backoff(attempt, retry_after=None)
                continue
            raise AdvboxUnexpectedResponse(f"HTTP {status}: status não previsto")

        raise AssertionError("loop de retentativas terminou sem resultado")

    async def _backoff(self, attempt: int, *, retry_after: str | None) -> None:
        parsed_retry_after: float | None = None
        if retry_after is not None:
            try:
                parsed_retry_after = float(retry_after)
            except ValueError:
                try:
                    deadline = parsedate_to_datetime(retry_after)
                    parsed_retry_after = (deadline - datetime.now(UTC)).total_seconds()
                except (TypeError, ValueError):
                    parsed_retry_after = None
        if parsed_retry_after is not None and not math.isfinite(parsed_retry_after):
            parsed_retry_after = None
        exponential = min(30.0, 2.0**attempt)
        delay = parsed_retry_after if parsed_retry_after is not None else exponential
        delay = max(0.0, delay) + self._random_value()
        await self._sleep(delay)


class AdvboxClient:
    """Production-facing allowlist of confirmed, read-only collection endpoints."""

    _ENDPOINTS = {
        "customers": "/customers",
        "lawsuits": "/lawsuits",
        "transactions": "/transactions",
        "last_movements": "/last_movements",
    }

    def __init__(self, settings: AdvboxAuditSettings, **kwargs: Any) -> None:
        self._transport = AdvboxAuditClient(settings, **kwargs)

    async def __aenter__(self) -> "AdvboxClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._transport.aclose()

    @property
    def metrics(self) -> RequestMetrics:
        return self._transport.metrics

    async def list_page(self, resource: str, *, limit: int, offset: int) -> SafeHttpResult:
        if resource not in self._ENDPOINTS or not 1 <= limit <= 100 or offset < 0:
            raise ValueError("recurso ou paginação fora do contrato confirmado")
        return await self._transport.get(
            self._ENDPOINTS[resource], params={"limit": limit, "offset": offset}
        )

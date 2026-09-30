import asyncio
from pathlib import Path

import pytest

from partner_reports.integrations.advbox.client import AdvboxAuthenticationError
from partner_reports.jobs import automation_cli


def _fake_work(results: list[str]):
    calls: list[int] = []

    async def fake(settings, sessions, output_root: Path) -> str:
        calls.append(1)
        return results.pop(0) if results else "report:empty"

    return fake, calls


def test_private_drain_stops_when_both_queues_are_empty(monkeypatch) -> None:
    fake, calls = _fake_work(["import:succeeded", "report:succeeded", "report:empty"])
    monkeypatch.setattr(automation_cli, "_process_private_work", fake)

    counts = asyncio.run(automation_cli._drain_private(None, None, Path("unused")))

    assert counts == {"import:succeeded": 1, "report:succeeded": 1}
    assert len(calls) == 3


def test_check_advbox_reports_missing_token_without_calling_api(monkeypatch) -> None:
    monkeypatch.delenv("ADVBOX_API_TOKEN", raising=False)
    real_settings = automation_cli.AdvboxAuditSettings
    monkeypatch.setattr(
        automation_cli, "AdvboxAuditSettings", lambda: real_settings(_env_file=None)
    )

    def no_client(*_args, **_kwargs):
        raise AssertionError("nenhuma chamada deve ocorrer sem token")

    monkeypatch.setattr(automation_cli, "AdvboxClient", no_client)
    assert asyncio.run(automation_cli._check_advbox()) == "token_missing_or_invalid"


@pytest.mark.parametrize(
    ("error", "expected"),
    [(None, "ok"), (AdvboxAuthenticationError("synthetic"), "AdvboxAuthenticationError")],
)
def test_check_advbox_uses_one_get_and_reports_only_error_class(
    monkeypatch, error: Exception | None, expected: str
) -> None:
    calls: list[tuple[str, int, int]] = []

    class FakeClient:
        def __init__(self, _settings) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def list_page(self, resource: str, *, limit: int, offset: int):
            calls.append((resource, limit, offset))
            if error is not None:
                raise error

    monkeypatch.setenv("ADVBOX_API_TOKEN", "synthetic-token-not-real")
    monkeypatch.setattr(automation_cli, "AdvboxClient", FakeClient)
    assert asyncio.run(automation_cli._check_advbox()) == expected
    assert calls == [("lawsuits", 1, 0)]


@pytest.mark.parametrize("result", ["import:succeeded", "import:failed", "report:failed"])
def test_private_drain_is_bounded_per_scheduled_run(monkeypatch, result: str) -> None:
    fake, calls = _fake_work([result] * 50)
    monkeypatch.setattr(automation_cli, "_process_private_work", fake)

    counts = asyncio.run(automation_cli._drain_private(None, None, Path("unused")))

    assert counts == {result: automation_cli._DRAIN_LIMIT}
    assert len(calls) == automation_cli._DRAIN_LIMIT

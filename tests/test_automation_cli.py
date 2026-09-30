import asyncio
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("result", ["import:succeeded", "import:failed", "report:failed"])
def test_private_drain_is_bounded_per_scheduled_run(monkeypatch, result: str) -> None:
    fake, calls = _fake_work([result] * 50)
    monkeypatch.setattr(automation_cli, "_process_private_work", fake)

    counts = asyncio.run(automation_cli._drain_private(None, None, Path("unused")))

    assert counts == {result: automation_cli._DRAIN_LIMIT}
    assert len(calls) == automation_cli._DRAIN_LIMIT

from __future__ import annotations

from threading import Event
from typing import TYPE_CHECKING
from unittest.mock import Mock

import anyio
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from quantinue import main
from quantinue.core.config import Settings
from quantinue.db.memory import InMemoryRunStore
from quantinue.orchestration.policy import Mvp2Config, load_mvp2_config
from quantinue.runtime_status import RuntimeSnapshot

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class IsolatedSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, env_prefix="QUANTINUE_", extra="ignore")


class _Runner:
    def __init__(self) -> None:
        self.started = Event()
        self.cancelled = Event()
        self.jobs = ()

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot.owner(
            daily_attached=False,
            watch_attached=True,
            rejudge_configured=False,
            stream_configured=False,
        )

    async def run_forever(self) -> None:
        self.started.set()
        try:
            await anyio.sleep_forever()
        finally:
            self.cancelled.set()


class _OwnerStore(InMemoryRunStore):
    domain = Mock()


def test_background_workers_default_to_disabled_without_reading_dotenv() -> None:
    # Given / When
    settings = IsolatedSettings()

    # Then
    assert not settings.background_workers


def test_false_does_not_construct_worker_only_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    market_data_factory = Mock()
    analyzer_factory = Mock()
    job_factory = Mock()
    watch_factory = Mock()
    heartbeat_factory = Mock()
    monkeypatch.setattr(main, "build_market_data", market_data_factory)
    monkeypatch.setattr(main, "build_budgeted_analyzer", analyzer_factory)
    monkeypatch.setattr(main, "build_job_runner", job_factory)
    monkeypatch.setattr(main, "build_watch_runner", watch_factory)
    monkeypatch.setattr(main, "build_heartbeat_reporter", heartbeat_factory)

    # When
    app = main.create_app(IsolatedSettings(background_workers=False), store=InMemoryRunStore())
    with TestClient(app):
        pass

    # Then
    market_data_factory.assert_not_called()
    analyzer_factory.assert_not_called()
    job_factory.assert_not_called()
    watch_factory.assert_not_called()
    heartbeat_factory.assert_not_called()


def test_true_starts_and_cancels_every_configured_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    jobs = _Runner()
    watch = _Runner()
    heartbeat = _Runner()
    def enabled_config(path: Path) -> Mvp2Config:
        config = load_mvp2_config(path)
        return config.model_copy(
            update={
                "watch": config.watch.model_copy(update={"enabled": True}),
            }
        )

    monkeypatch.setattr(main, "load_mvp2_config", enabled_config)
    monkeypatch.setattr(main, "build_budgeted_analyzer", Mock(return_value=None))
    monkeypatch.setattr(main, "build_job_runner", Mock(return_value=jobs))
    monkeypatch.setattr(main, "build_watch_runner", Mock(return_value=watch))
    monkeypatch.setattr(main, "build_heartbeat_reporter", Mock(return_value=heartbeat))

    # When
    app = main.create_app(
        IsolatedSettings(
            background_workers=True,
            heartbeat_url=SecretStr(
                "https://hc-ping.com/00000000-0000-4000-8000-000000000001"
            ),
        ),
        store=_OwnerStore(),
    )
    with TestClient(app):
        assert jobs.started.wait(timeout=1)
        assert watch.started.wait(timeout=1)
        assert heartbeat.started.wait(timeout=1)

    # Then
    assert jobs.cancelled.wait(timeout=1)
    assert watch.cancelled.wait(timeout=1)
    assert heartbeat.cancelled.wait(timeout=1)

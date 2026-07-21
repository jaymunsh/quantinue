from datetime import UTC, datetime

import pytest

from quantinue.orchestration.policy import WatchConfig
from quantinue.orchestration.watch_runner import WatchRunner


@pytest.mark.anyio
async def test_watch_tick_is_ready_during_the_regular_session() -> None:
    # Given
    runner = WatchRunner(WatchConfig(enabled=True))

    # When
    outcome = await runner.tick(datetime(2026, 7, 20, 14, 0, tzinfo=UTC))

    # Then
    assert outcome.reason == "ready"


@pytest.mark.anyio
async def test_watch_tick_is_closed_before_the_regular_session() -> None:
    # Given
    runner = WatchRunner(WatchConfig(enabled=True))

    # When
    outcome = await runner.tick(datetime(2026, 7, 20, 12, 0, tzinfo=UTC))

    # Then
    assert outcome.reason == "market_closed"


@pytest.mark.anyio
async def test_watch_tick_is_closed_on_a_holiday() -> None:
    # Given
    runner = WatchRunner(WatchConfig(enabled=True))

    # When
    outcome = await runner.tick(datetime(2026, 7, 3, 14, 0, tzinfo=UTC))

    # Then
    assert outcome.reason == "market_closed"


@pytest.mark.anyio
async def test_disabled_watch_tick_is_completely_inert() -> None:
    # Given
    runner = WatchRunner(WatchConfig(enabled=False))

    # When
    outcome = await runner.tick(datetime(2026, 7, 20, 14, 0, tzinfo=UTC))

    # Then
    assert outcome.reason == "disabled"

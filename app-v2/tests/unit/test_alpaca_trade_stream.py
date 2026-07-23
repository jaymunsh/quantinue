from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import anyio
import pytest

from quantinue.market_data.alpaca_stream import AlpacaTradeStream
from quantinue.market_data.models import LatestTrade
from quantinue.orchestration.watch_policy import WatchStreamConfig


class _Socket:
    def __init__(self, messages: tuple[str, ...]) -> None:
        self._messages = iter(messages)
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        try:
            return next(self._messages)
        except StopIteration:
            await anyio.sleep_forever()
            raise AssertionError from None


@pytest.mark.anyio
async def test_stream_authenticates_subscribes_and_emits_a_normalized_trade() -> None:
    # Given
    socket = _Socket(
        (
            '[{"T":"success","msg":"connected"}]',
            '[{"T":"success","msg":"authenticated"}]',
            '[{"T":"subscription","trades":["BRK.B"]}]',
            '[{"T":"t","S":"BRK.B","p":501.25,"t":"2026-07-20T14:00:00Z"}]',
        )
    )

    @asynccontextmanager
    async def connect() -> AsyncGenerator[_Socket]:
        yield socket

    stream = AlpacaTradeStream(
        key_id="key",
        secret_key="secret",
        config=WatchStreamConfig(enabled=True),
        connector=connect,
    )
    seen: list[LatestTrade] = []
    consumed = anyio.Event()

    async def tickers() -> tuple[str, ...]:
        return ("BRK/B",)

    async def consume(trade: LatestTrade) -> None:
        seen.append(trade)
        consumed.set()

    # When
    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(stream.run, tickers, consume)
        await consumed.wait()
        task_group.cancel_scope.cancel()

    # Then
    assert '"action":"auth"' in socket.sent[0]
    assert '"trades":["BRK.B"]' in socket.sent[1]
    assert seen == [
        LatestTrade(
            ticker="BRK/B",
            price=Decimal("501.25"),
            observed_at=datetime(2026, 7, 20, 14, 0, tzinfo=UTC),
            source="alpaca-iex-stream",
        )
    ]


@pytest.mark.anyio
async def test_three_consecutive_connection_failures_enter_failed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StopProbeError(RuntimeError):
        pass

    @asynccontextmanager
    async def connect() -> AsyncGenerator[_Socket]:
        should_fail = True
        if should_fail:
            raise OSError
        yield _Socket(())

    stream = AlpacaTradeStream(
        key_id="key",
        secret_key="secret",
        config=WatchStreamConfig(enabled=True, reconnect_seconds=1),
        connector=connect,
    )
    observed: list[str] = []

    async def observe_sleep(_: float) -> None:
        observed.append(stream.state)
        if len(observed) == 3:
            raise _StopProbeError

    monkeypatch.setattr("quantinue.market_data.alpaca_stream.anyio.sleep", observe_sleep)

    async def tickers() -> tuple[str, ...]:
        return ()

    async def consume(_: LatestTrade) -> None:
        return None

    with pytest.raises(_StopProbeError):
        await stream.run(tickers, consume)

    assert observed == ["reconnecting", "reconnecting", "failed"]


@pytest.mark.anyio
async def test_zero_holdings_connect_without_a_subscription() -> None:
    # Given
    socket = _Socket(
        (
            '[{"T":"success","msg":"connected"}]',
            '[{"T":"success","msg":"authenticated"}]',
        )
    )
    stream = AlpacaTradeStream(
        key_id="key",
        secret_key="secret",
        config=WatchStreamConfig(enabled=True),
    )

    async def tickers() -> tuple[str, ...]:
        return ()

    async def consume(_: LatestTrade) -> None:
        return None

    # When
    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(stream._run_session, socket, tickers, consume)
        await anyio.lowlevel.checkpoint()
        task_group.cancel_scope.cancel()

    # Then
    assert stream.state == "connected"
    assert len(socket.sent) == 1
    assert '"action":"auth"' in socket.sent[0]


@pytest.mark.anyio
async def test_holding_changes_reconcile_on_the_configured_sixty_second_boundary() -> None:
    # Given
    socket = _Socket(())
    stream = AlpacaTradeStream(
        key_id="key",
        secret_key="secret",
        config=WatchStreamConfig(enabled=True, resubscribe_seconds=60),
    )

    # When
    subscribed = await stream._sync(socket, frozenset({"AAPL"}), ("MSFT",))

    # Then
    assert stream.config.resubscribe_seconds <= 60
    assert subscribed == frozenset({"MSFT"})
    assert socket.sent == [
        '{"action":"unsubscribe","trades":["AAPL"]}',
        '{"action":"subscribe","trades":["MSFT"]}',
    ]


@pytest.mark.anyio
async def test_failed_connection_waits_exactly_five_seconds_before_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    class _StopProbeError(RuntimeError):
        pass

    @asynccontextmanager
    async def connect() -> AsyncGenerator[_Socket]:
        raise OSError
        yield _Socket(())

    stream = AlpacaTradeStream(
        key_id="key",
        secret_key="secret",
        config=WatchStreamConfig(enabled=True, reconnect_seconds=5),
        connector=connect,
    )
    waits: list[float] = []

    async def observe_sleep(seconds: float) -> None:
        waits.append(seconds)
        raise _StopProbeError

    monkeypatch.setattr("quantinue.market_data.alpaca_stream.anyio.sleep", observe_sleep)

    async def tickers() -> tuple[str, ...]:
        return ()

    async def consume(_: LatestTrade) -> None:
        return None

    # When / Then
    with pytest.raises(_StopProbeError):
        await stream.run(tickers, consume)
    assert waits == [5]

from datetime import UTC, datetime
from decimal import Decimal

import httpx as httpx2
import pytest

from quantinue.market_data.alpaca_quotes import AlpacaQuoteSource


@pytest.mark.anyio
async def test_latest_trades_are_fetched_in_one_batch() -> None:
    # Given
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200,
            json={
                "trades": {
                    "AAA": {"p": 101.25, "t": "2026-07-20T14:00:00Z"},
                    "BBB": {"p": 52.5, "t": "2026-07-20T14:00:01Z"},
                }
            },
        )

    source = AlpacaQuoteSource(
        key_id="key", secret_key="secret", transport=httpx2.MockTransport(handler)
    )

    # When
    trades = await source.latest_trades(("AAA", "BBB"))

    # Then
    assert len(seen) == 1
    assert seen[0].url.params["symbols"] == "AAA,BBB"
    assert seen[0].url.params["feed"] == "iex"
    assert [(trade.ticker, trade.price) for trade in trades] == [
        ("AAA", Decimal("101.25")),
        ("BBB", Decimal("52.5")),
    ]
    assert trades[0].observed_at == datetime(2026, 7, 20, 14, 0, tzinfo=UTC)


@pytest.mark.anyio
async def test_latest_trades_use_headers_and_restore_share_class_symbols() -> None:
    # Given
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200,
            json={"trades": {"BRK.B": {"p": 500.0, "t": "2026-07-20T14:00:00Z"}}},
        )

    source = AlpacaQuoteSource(
        key_id="key-1", secret_key="secret-1", transport=httpx2.MockTransport(handler)
    )

    # When
    trades = await source.latest_trades(("BRK/B",))

    # Then
    assert seen[0].url.params["symbols"] == "BRK.B"
    assert seen[0].headers["APCA-API-KEY-ID"] == "key-1"
    assert "secret-1" not in str(seen[0].url)
    assert trades[0].ticker == "BRK/B"


@pytest.mark.anyio
async def test_invalid_or_absent_latest_trades_are_not_invented() -> None:
    # Given
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "trades": {
                    "BAD_PRICE": {"p": 0, "t": "2026-07-20T14:00:00Z"},
                    "BAD_TIME": {"p": 10, "t": "not-a-time"},
                }
            },
        )

    source = AlpacaQuoteSource(
        key_id="key", secret_key="secret", transport=httpx2.MockTransport(handler)
    )

    # When
    trades = await source.latest_trades(("BAD_PRICE", "BAD_TIME", "ABSENT"))

    # Then
    assert trades == ()

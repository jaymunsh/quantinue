from decimal import Decimal

import pytest

from quantinue.market_data.fixture import FixtureMarketData


@pytest.mark.anyio
async def test_fixture_latest_trades_are_deterministic() -> None:
    # Given
    source = FixtureMarketData()

    # When
    trades = await source.latest_trades(("NVDA", "AAPL"))

    # Then
    assert [(trade.ticker, trade.price) for trade in trades] == [
        ("NVDA", Decimal(151)),
        ("AAPL", Decimal(151)),
    ]

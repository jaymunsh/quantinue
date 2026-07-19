"""The mock broker must be able to answer tradability too.

Without it the halted guard is not merely unverified in dry runs — it is
structurally unreachable, because role 10 treats a broker lacking the
capability as "tradable" and never asks. A defence that cannot fire outside
production is a defence nobody has ever seen work.
"""

import pytest

from quantinue.broker.contracts import TradabilityBroker
from quantinue.broker.mock import MockBroker


def test_mock_broker_advertises_the_tradability_capability() -> None:
    assert isinstance(MockBroker(), TradabilityBroker)


@pytest.mark.anyio
async def test_everything_is_tradable_by_default() -> None:
    assert await MockBroker().is_tradable("NVDA") is True


@pytest.mark.anyio
async def test_configured_symbols_report_as_halted() -> None:
    broker = MockBroker(halted_tickers=frozenset({"NVDA"}))

    assert await broker.is_tradable("NVDA") is False
    assert await broker.is_tradable("AAPL") is True


@pytest.mark.anyio
async def test_halted_lookup_is_case_insensitive() -> None:
    broker = MockBroker(halted_tickers=frozenset({"nvda"}))

    assert await broker.is_tradable("NVDA") is False

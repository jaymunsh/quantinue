"""Batch latest-trade collection from Alpaca for intraday watching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import httpx as httpx2
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from quantinue.core.schemas import AwareDateTime  # noqa: TC001
from quantinue.market_data.models import LatestTrade
from quantinue.market_data.symbols import to_venue_symbol

_LATEST_TRADES_URL: Final = "https://data.alpaca.markets/v2/stocks/trades/latest"
_SOURCE: Final = "alpaca-iex"
_DEFAULT_SYMBOLS_PER_REQUEST: Final = 200


class _TradeWire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    price: float = Field(alias="p", gt=0)
    observed_at: AwareDateTime = Field(alias="t")


class _LatestTradesWire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    trades: dict[str, JsonValue] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlpacaQuoteSource:
    """Fetch recent trades for many symbols with bounded batch requests."""

    key_id: str
    secret_key: str
    transport: httpx2.AsyncBaseTransport | None = None
    symbols_per_request: int = _DEFAULT_SYMBOLS_PER_REQUEST
    timeout_seconds: float = 30.0

    async def latest_trades(self, tickers: tuple[str, ...]) -> tuple[LatestTrade, ...]:
        """Return valid trades the venue reported without inventing missing symbols."""
        if not tickers:
            return ()
        collected: list[LatestTrade] = []
        async with httpx2.AsyncClient(
            transport=self.transport,
            timeout=self.timeout_seconds,
            headers={
                "APCA-API-KEY-ID": self.key_id,
                "APCA-API-SECRET-KEY": self.secret_key,
            },
        ) as client:
            for chunk in self._chunks(tickers):
                venue_to_ours = {to_venue_symbol(ticker): ticker for ticker in chunk}
                response = await client.get(
                    _LATEST_TRADES_URL,
                    params={"symbols": ",".join(venue_to_ours), "feed": "iex"},
                )
                _ = response.raise_for_status()
                payload = _LatestTradesWire.model_validate(response.json())
                for venue_symbol, raw_trade in payload.trades.items():
                    try:
                        trade = _TradeWire.model_validate(raw_trade)
                    except ValidationError:
                        continue
                    ticker = venue_to_ours.get(venue_symbol)
                    if ticker is None:
                        continue
                    collected.append(
                        LatestTrade(
                            ticker=ticker,
                            price=trade.price,
                            observed_at=trade.observed_at,
                            source=_SOURCE,
                        )
                    )
        return tuple(collected)

    def _chunks(self, tickers: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
        size = max(1, self.symbols_per_request)
        return tuple(
            tickers[index : index + size] for index in range(0, len(tickers), size)
        )

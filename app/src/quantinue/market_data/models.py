"""Typed market-data values and adapter contract."""

from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from quantinue.core.schemas import AwareDateTime


class BoundaryModel(BaseModel):
    """Immutable value parsed at an external-data boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class Provenance(BoundaryModel):
    """Origin, timing, confidence, and execution lineage."""

    source: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    observed_at: AwareDateTime
    captured_at: AwareDateTime
    confidence: float = Field(ge=0, le=1)
    execution_id: str = Field(min_length=1)


class SecuritySnapshot(BoundaryModel):
    """One equity row returned by the universe screener."""

    ticker: str = Field(min_length=1, max_length=12)
    name: str = Field(min_length=1)
    market_cap: Decimal = Field(ge=0)
    last_price: Decimal = Field(ge=0)
    volume: int = Field(ge=0)
    provenance: Provenance


class Candle(BoundaryModel):
    """One normalized OHLCV observation."""

    ticker: str = Field(min_length=1, max_length=12)
    opened_at: AwareDateTime
    open: Decimal = Field(ge=0)
    high: Decimal = Field(ge=0)
    low: Decimal = Field(ge=0)
    close: Decimal = Field(ge=0)
    volume: int = Field(ge=0)
    provenance: Provenance


class MacroObservation(BoundaryModel):
    """One named macroeconomic series observation."""

    series: str = Field(min_length=1)
    observed_at: AwareDateTime
    value: Decimal
    provenance: Provenance


class SecSubmission(BoundaryModel):
    """One recent SEC filing from the submissions feed."""

    cik: str = Field(pattern=r"^\d{10}$")
    company_name: str = Field(min_length=1)
    accession_number: str = Field(min_length=1)
    form: str = Field(min_length=1)
    filed_at: AwareDateTime
    primary_document: str = Field(min_length=1)
    provenance: Provenance


class NewsItem(BoundaryModel):
    """RSS-safe title, snippet, and link without article crawling."""

    title: str = Field(min_length=1)
    snippet: str
    url: str = Field(min_length=1)
    published_at: AwareDateTime
    provenance: Provenance


class MarketData(Protocol):
    """Common contract implemented by fixture and public sources."""

    async def screener(self, execution_id: str) -> tuple[SecuritySnapshot, ...]:  # noqa: D102
        ...

    async def candles(self, ticker: str, execution_id: str) -> tuple[Candle, ...]:  # noqa: D102
        ...

    async def macro(self, series: str, execution_id: str) -> tuple[MacroObservation, ...]:  # noqa: D102
        ...

    async def sec_submissions(self, cik: str, execution_id: str) -> tuple[SecSubmission, ...]:  # noqa: D102
        ...

    async def rss(self, execution_id: str) -> tuple[NewsItem, ...]:  # noqa: D102
        ...

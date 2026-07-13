"""No-key public HTTP market-data adapters."""

import csv
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from io import StringIO
from xml.etree import ElementTree as ET

import httpx2
from pydantic import BaseModel, ConfigDict
from typing_extensions import override

from quantinue.market_data.models import (
    Candle,
    MacroObservation,
    NewsItem,
    Provenance,
    SecSubmission,
    SecuritySnapshot,
)


@dataclass(frozen=True, slots=True)
class MarketDataEndpoints:
    """Configurable no-key public feed endpoints."""

    screener_url: str
    candles_url: str
    macro_url: str
    sec_url: str
    rss_url: str

    @classmethod
    def defaults(cls) -> "MarketDataEndpoints":
        """Return public endpoints that do not require secrets."""
        return cls(
            screener_url="https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=2000",
            candles_url="https://stooq.com/q/d/l/?s={ticker}&i=d",
            macro_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}",
            sec_url="https://data.sec.gov/submissions/CIK{cik}.json",
            rss_url="https://www.sec.gov/news/pressreleases.rss",
        )


@dataclass(frozen=True, slots=True)
class MarketDataFetchError(Exception):
    """Public feed returned an unsuccessful HTTP response."""

    source: str
    status_code: int

    @override
    def __str__(self) -> str:
        """Render source and status without leaking response content."""
        return f"{self.source} returned HTTP {self.status_code}"


class _Boundary(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _NasdaqRow(_Boundary):
    symbol: str
    name: str
    marketCap: Decimal = Decimal(0)  # noqa: N815 - upstream spelling
    lastsale: str = "$0"
    volume: int = 0


class _NasdaqData(_Boundary):
    rows: tuple[_NasdaqRow, ...]


class _NasdaqResponse(_Boundary):
    data: _NasdaqData


class _CandleRow(_Boundary):
    datetime: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class _CandleResponse(_Boundary):
    values: tuple[_CandleRow, ...]


class _MacroRow(_Boundary):
    date: str
    value: Decimal


class _MacroResponse(_Boundary):
    observations: tuple[_MacroRow, ...]


class _SecRecent(_Boundary):
    accessionNumber: tuple[str, ...]  # noqa: N815 - upstream spelling
    filingDate: tuple[str, ...]  # noqa: N815 - upstream spelling
    form: tuple[str, ...]
    primaryDocument: tuple[str, ...]  # noqa: N815 - upstream spelling


class _SecFilings(_Boundary):
    recent: _SecRecent


class _SecResponse(_Boundary):
    cik: str
    name: str
    filings: _SecFilings


class HttpMarketData:
    """Fetch and parse optional public feeds using one owned HTTP client."""

    def __init__(
        self,
        client: httpx2.AsyncClient,
        endpoints: MarketDataEndpoints,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Take ownership of a client until context exit."""
        self._client = client
        self._endpoints = endpoints
        self._clock = clock or (lambda: datetime.now(UTC))

    async def aclose(self) -> None:
        """Close the owned HTTP client at application shutdown."""
        await self._client.aclose()

    async def _get(self, source: str, url: str) -> httpx2.Response:
        response = await self._client.get(url)
        if response.is_error:
            raise MarketDataFetchError(source, response.status_code)
        return response

    def _provenance(
        self, source: str, ref: str, observed_at: datetime, execution_id: str
    ) -> Provenance:
        return Provenance(
            source=source,
            source_ref=ref,
            observed_at=observed_at,
            captured_at=self._clock(),
            confidence=0.9,
            execution_id=execution_id,
        )

    async def screener(self, execution_id: str) -> tuple[SecuritySnapshot, ...]:
        """Fetch and parse the NASDAQ universe."""
        response = await self._get("nasdaq-screener", self._endpoints.screener_url)
        payload = _NasdaqResponse.model_validate_json(response.content)
        at = self._clock()
        return tuple(
            SecuritySnapshot(
                ticker=row.symbol.upper(),
                name=row.name,
                market_cap=row.marketCap,
                last_price=Decimal(row.lastsale.removeprefix("$").replace(",", "")),
                volume=row.volume,
                provenance=self._provenance("nasdaq-screener", str(response.url), at, execution_id),
            )
            for row in payload.data.rows
        )

    async def candles(self, ticker: str, execution_id: str) -> tuple[Candle, ...]:
        """Fetch normalized daily candles."""
        url = self._endpoints.candles_url.format(ticker=ticker.upper())
        response = await self._get("market-candles", url)
        rows = _candle_rows(response)
        return tuple(
            Candle(
                ticker=ticker.upper(),
                opened_at=_date(row.datetime),
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                provenance=self._provenance(
                    "market-candles", str(response.url), _date(row.datetime), execution_id
                ),
            )
            for row in rows
        )

    async def macro(self, series: str, execution_id: str) -> tuple[MacroObservation, ...]:
        """Fetch a public macro series."""
        response = await self._get("macro-feed", self._endpoints.macro_url.format(series=series))
        rows = _macro_rows(response)
        return tuple(
            MacroObservation(
                series=series,
                observed_at=_date(row.date),
                value=row.value,
                provenance=self._provenance(
                    "macro-feed", str(response.url), _date(row.date), execution_id
                ),
            )
            for row in rows
        )

    async def sec_submissions(self, cik: str, execution_id: str) -> tuple[SecSubmission, ...]:
        """Fetch recent SEC submissions for one CIK."""
        response = await self._get(
            "sec-submissions", self._endpoints.sec_url.format(cik=cik.zfill(10))
        )
        payload = _SecResponse.model_validate_json(response.content)
        recent = payload.filings.recent
        rows = zip(
            recent.accessionNumber,
            recent.filingDate,
            recent.form,
            recent.primaryDocument,
            strict=True,
        )
        return tuple(
            SecSubmission(
                cik=payload.cik.zfill(10),
                company_name=payload.name,
                accession_number=accession,
                form=form,
                filed_at=_date(filed),
                primary_document=document,
                provenance=self._provenance(
                    "sec-submissions", str(response.url), _date(filed), execution_id
                ),
            )
            for accession, filed, form, document in rows
        )

    async def rss(self, execution_id: str) -> tuple[NewsItem, ...]:
        """Fetch RSS titles and snippets without crawling articles."""
        response = await self._get("rss", self._endpoints.rss_url)
        root = ET.fromstring(response.content)  # noqa: S314 - trusted configured public feed
        items: list[NewsItem] = []
        for node in root.findall(".//item"):
            published = parsedate_to_datetime(node.findtext("pubDate", default=""))
            url = node.findtext("link", default="")
            items.append(
                NewsItem(
                    title=node.findtext("title", default=""),
                    snippet=node.findtext("description", default=""),
                    url=url,
                    published_at=published,
                    provenance=self._provenance("rss", url, published, execution_id),
                )
            )
        return tuple(items)


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _candle_rows(response: httpx2.Response) -> tuple[_CandleRow, ...]:
    if response.content.lstrip().startswith(b"{"):
        return _CandleResponse.model_validate_json(response.content).values
    records = csv.DictReader(StringIO(response.text))
    return tuple(
        _CandleRow.model_validate(
            {
                "datetime": row["Date"],
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
                "volume": row["Volume"],
            }
        )
        for row in records
    )


def _macro_rows(response: httpx2.Response) -> tuple[_MacroRow, ...]:
    if response.content.lstrip().startswith(b"{"):
        return _MacroResponse.model_validate_json(response.content).observations
    records = csv.DictReader(StringIO(response.text))
    return tuple(
        _MacroRow.model_validate({"date": row["DATE"], "value": tuple(row.values())[-1]})
        for row in records
        if tuple(row.values())[-1] != "."
    )

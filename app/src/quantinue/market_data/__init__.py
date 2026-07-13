"""Optional public market feeds with deterministic offline defaults."""

from quantinue.market_data.fixture import FixtureMarketData
from quantinue.market_data.http_client import (
    HTTP_CLIENT_POLICY,
    HttpClientPolicy,
    build_http_client,
    public_http_client,
)
from quantinue.market_data.http_source import (
    HttpMarketData,
    MarketDataEndpoints,
    MarketDataFetchError,
)
from quantinue.market_data.models import (
    Candle,
    MacroObservation,
    MarketData,
    NewsItem,
    Provenance,
    SecSubmission,
    SecuritySnapshot,
)

__all__ = [
    "HTTP_CLIENT_POLICY",
    "Candle",
    "FixtureMarketData",
    "HttpClientPolicy",
    "HttpMarketData",
    "MacroObservation",
    "MarketData",
    "MarketDataEndpoints",
    "MarketDataFetchError",
    "NewsItem",
    "Provenance",
    "SecSubmission",
    "SecuritySnapshot",
    "build_http_client",
    "public_http_client",
]

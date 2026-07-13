"""Market-data adapters stay deterministic offline and parse wire responses."""

from datetime import UTC, datetime
from decimal import Decimal

import httpx2
import pytest
from pydantic import ValidationError

from quantinue.broker.mock import MockBroker
from quantinue.core.config import DataMode, Settings
from quantinue.db.store import InMemoryRunStore
from quantinue.llm.provider import DeterministicAnalyzer
from quantinue.market_data import (
    HTTP_CLIENT_POLICY,
    FixtureMarketData,
    HttpMarketData,
    MarketDataEndpoints,
    build_http_client,
)
from quantinue.orchestration.factory import build_market_data, build_roles
from quantinue.orchestration.pipeline import PipelineOrchestrator
from quantinue.roles.role_01_universe_screener.service import UniverseScreener
from quantinue.roles.role_02_technical_analysis.service import TechnicalAnalysis
from quantinue.roles.role_04_macro_analysis.service import MacroAnalysis
from quantinue.roles.role_05_disclosure_analysis.service import DisclosureAnalysis
from quantinue.roles.role_06_news_analysis.service import NewsAnalysis


def test_owned_http_factory_exposes_required_transport_policy() -> None:
    # Given / When
    policy = HTTP_CLIENT_POLICY

    # Then
    assert policy.http2 is True
    assert policy.retries == 3
    assert policy.max_connections == 200
    assert policy.max_keepalive_connections == 40
    assert policy.keepalive_expiry == 30.0
    assert policy.connect_timeout == 5.0
    assert policy.read_timeout == 30.0
    assert policy.write_timeout == 10.0
    assert policy.pool_timeout == 10.0
    assert policy.tcp_nodelay == 1


@pytest.mark.anyio
async def test_fixture_returns_stable_no_key_snapshot() -> None:
    # Given
    source = FixtureMarketData()

    # When
    first = await source.screener("run-1")
    second = await source.screener("run-1")

    # Then
    assert first == second
    assert first[0].ticker == "NVDA"
    assert first[0].provenance.execution_id == "run-1"
    assert first[0].provenance.source == "fixture:nasdaq-screener"


def test_data_mode_selects_fixture_or_public_adapter() -> None:
    # Given / When
    fixture = build_market_data(Settings(data_mode=DataMode.FIXTURE))
    public = build_market_data(Settings(data_mode=DataMode.PUBLIC))

    # Then
    assert isinstance(fixture, FixtureMarketData)
    assert isinstance(public, HttpMarketData)


@pytest.mark.anyio
async def test_public_market_data_is_injected_into_all_data_roles() -> None:
    # Given
    source = HttpMarketData(
        build_http_client(
            transport=httpx2.MockTransport(lambda request: httpx2.Response(200, request=request))
        ),
        MarketDataEndpoints.defaults(),
    )

    # When
    roles = build_roles(DeterministicAnalyzer(), broker=MockBroker(), market_data=source)

    # Then
    assert isinstance(roles[0], UniverseScreener)
    assert isinstance(roles[1], TechnicalAnalysis)
    assert isinstance(roles[3], MacroAnalysis)
    assert isinstance(roles[4], DisclosureAnalysis)
    assert isinstance(roles[5], NewsAnalysis)
    assert roles[0].market_data is source
    assert roles[1].market_data is source
    assert roles[3].market_data is source
    assert roles[4].market_data is source
    assert roles[5].market_data is source
    await source.aclose()


def test_explicit_fixture_provider_is_not_hidden_by_composition() -> None:
    # Given
    source = FixtureMarketData()

    # When
    roles = build_roles(DeterministicAnalyzer(), MockBroker(), source)

    # Then
    assert isinstance(roles[0], UniverseScreener)
    assert isinstance(roles[1], TechnicalAnalysis)
    assert isinstance(roles[3], MacroAnalysis)
    assert isinstance(roles[4], DisclosureAnalysis)
    assert isinstance(roles[5], NewsAnalysis)
    assert roles[0].market_data is source
    assert roles[1].market_data is source
    assert roles[3].market_data is source
    assert roles[4].market_data is source
    assert roles[5].market_data is source


@pytest.mark.anyio
async def test_orchestrator_closes_owned_public_market_data() -> None:
    # Given
    client = build_http_client(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, request=request))
    )
    source = HttpMarketData(
        client,
        MarketDataEndpoints.defaults(),
    )
    orchestrator = PipelineOrchestrator((), InMemoryRunStore())
    orchestrator.own_resource(source)

    # When
    await orchestrator.close()

    # Then
    assert client.is_closed is True


def test_public_defaults_require_no_secret_query_parameters() -> None:
    # Given / When
    endpoints = MarketDataEndpoints.defaults()

    # Then
    assert "apikey" not in endpoints.candles_url.lower()
    assert "api_key" not in endpoints.macro_url.lower()


@pytest.mark.anyio
async def test_http_adapters_parse_public_feeds_at_wire_boundary() -> None:
    # Given
    observed = datetime(2026, 7, 10, 20, tzinfo=UTC)
    responses = {
        "/screener": httpx2.Response(
            200,
            json={
                "data": {
                    "rows": [
                        {
                            "symbol": "nvda",
                            "name": "NVIDIA",
                            "marketCap": "1000",
                            "lastsale": "$150.25",
                            "volume": "42",
                        }
                    ]
                }
            },
        ),
        "/candles/NVDA": httpx2.Response(
            200,
            json={
                "values": [
                    {
                        "datetime": "2026-07-10",
                        "open": "149",
                        "high": "152",
                        "low": "148",
                        "close": "151",
                        "volume": "100",
                    }
                ]
            },
        ),
        "/macro": httpx2.Response(
            200, json={"observations": [{"date": "2026-07-10", "value": "4.25"}]}
        ),
        "/sec/0001045810.json": httpx2.Response(
            200,
            json={
                "cik": "0001045810",
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001"],
                        "filingDate": ["2026-07-10"],
                        "form": ["8-K"],
                        "primaryDocument": ["x.htm"],
                    }
                },
            },
        ),
        "/feed.xml": httpx2.Response(
            200,
            text=(
                "<rss><channel><item><title>NVIDIA update</title>"
                "<link>https://example.test/nvda</link>"
                "<description>Short snippet</description>"
                "<pubDate>Fri, 10 Jul 2026 20:00:00 GMT</pubDate>"
                "</item></channel></rss>"
            ),
        ),
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        return responses[request.url.path]

    client = build_http_client(transport=httpx2.MockTransport(handler))
    endpoints = MarketDataEndpoints(
        screener_url="https://wire.test/screener",
        candles_url="https://wire.test/candles/{ticker}",
        macro_url="https://wire.test/macro",
        sec_url="https://wire.test/sec/{cik}.json",
        rss_url="https://wire.test/feed.xml",
    )

    # When
    source = HttpMarketData(client, endpoints, clock=lambda: observed)
    universe = await source.screener("run-2")
    candles = await source.candles("NVDA", "run-2")
    macro = await source.macro("DFF", "run-2")
    filings = await source.sec_submissions("0001045810", "run-2")
    news = await source.rss("run-2")
    await source.aclose()

    assert client.is_closed

    # Then
    assert universe[0].market_cap == Decimal(1000)
    assert candles[0].close == Decimal(151)
    assert macro[0].value == Decimal("4.25")
    assert filings[0].form == "8-K"
    assert news[0].snippet == "Short snippet"
    assert all(
        item.provenance.captured_at == observed
        for item in (*universe, *candles, *macro, *filings, *news)
    )


@pytest.mark.anyio
async def test_http_failure_is_typed_with_source_context() -> None:
    # Given
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503, request=request)

    client = build_http_client(transport=httpx2.MockTransport(handler))
    endpoints = MarketDataEndpoints.defaults()

    # When / Then
    source = HttpMarketData(client, endpoints)
    with pytest.raises(Exception, match=r"nasdaq-screener.*503"):
        _ = await source.screener("run-3")
    await source.aclose()


@pytest.mark.anyio
async def test_malformed_wire_payload_is_rejected_at_boundary() -> None:
    # Given
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"data": {"rows": [{"name": "missing ticker"}]}})

    client = build_http_client(transport=httpx2.MockTransport(handler))

    # When / Then
    source = HttpMarketData(client, MarketDataEndpoints.defaults())
    with pytest.raises(ValidationError):
        _ = await source.screener("malformed-run")
    await source.aclose()

    assert client.is_closed

"""Public data composition runs end to end against a fake HTTP wire."""

from datetime import UTC, datetime

import httpx2
import pytest

from quantinue.broker.mock import MockBroker
from quantinue.core.config import DataMode, Settings
from quantinue.core.contracts import PipelineRequest
from quantinue.db.store import InMemoryRunStore
from quantinue.llm.provider import DeterministicAnalyzer
from quantinue.market_data import HttpMarketData
from quantinue.orchestration.factory import build_market_data, build_roles
from quantinue.orchestration.pipeline import PipelineOrchestrator


def _public_response(request: httpx2.Request) -> httpx2.Response:
    host = request.url.host
    if host == "api.nasdaq.com":
        payload = {
            "data": {
                "rows": [
                    {
                        "symbol": "NVDA",
                        "name": "NVIDIA",
                        "marketCap": "1000",
                        "lastsale": "$150",
                        "volume": 42,
                    }
                ]
            }
        }
        return httpx2.Response(200, json=payload, request=request)
    if host == "stooq.com":
        csv = "Date,Open,High,Low,Close,Volume\n2026-07-10,149,152,148,151,100\n"
        return httpx2.Response(200, text=csv, request=request)
    if host == "fred.stlouisfed.org":
        return httpx2.Response(200, text="DATE,DFF\n2026-07-10,4.25\n", request=request)
    if host == "data.sec.gov":
        recent = {
            "accessionNumber": ["0001"],
            "filingDate": ["2026-07-10"],
            "form": ["8-K"],
            "primaryDocument": ["x.htm"],
        }
        payload = {"cik": "1045810", "name": "NVIDIA CORP", "filings": {"recent": recent}}
        return httpx2.Response(200, json=payload, request=request)
    rss = (
        "<rss><channel><item><title>NVIDIA update</title>"
        "<link>https://example.test/nvda</link><description>Short snippet</description>"
        "<pubDate>Fri, 10 Jul 2026 20:00:00 GMT</pubDate></item></channel></rss>"
    )
    return httpx2.Response(200, text=rss, request=request)


@pytest.mark.anyio
async def test_public_mode_runs_pipeline_through_fake_http_wire() -> None:
    # Given
    settings = Settings(data_mode=DataMode.PUBLIC)
    source = build_market_data(settings, httpx2.MockTransport(_public_response))
    assert isinstance(source, HttpMarketData)
    roles = build_roles(DeterministicAnalyzer(), MockBroker(), source)
    orchestrator = PipelineOrchestrator(roles, InMemoryRunStore())

    # When
    result = await orchestrator.run(
        PipelineRequest(ticker="NVDA", cycle_ts=datetime(2026, 7, 10, 20, tzinfo=UTC))
    )
    await source.aclose()

    # Then
    data_traces = tuple(
        item for item in result.evidence_trace if item.component in {"01", "02", "04", "05", "06"}
    )
    assert len(result.stages) == 11
    assert tuple(item.source for item in data_traces) == (
        "nasdaq-screener",
        "market-candles",
        "macro-feed",
        "sec-submissions",
        "rss",
    )
    assert all(item.source_ref.startswith("https://") for item in data_traces)
    assert all(item.observed_at <= item.captured_at == result.cycle_ts for item in data_traces)
    assert all(item.confidence == 0.9 for item in data_traces)
    assert all(item.run_id == result.run_id for item in data_traces)

# pyright: reportPrivateUsage=false

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from quantinue.core.ontology import ModelProvider
from quantinue.db.domain_records import RawNewsWrite
from quantinue.db.postgres import PostgresRunStore
from quantinue.llm.budget import BudgetedAnalyzer
from quantinue.llm.provider import AnalysisMetadata, AnalysisResult, AnalysisTask
from quantinue.llm.usage_limits import MaximumTokenUsage, TokenUsage
from quantinue.orchestration.job_factory import JobSources, build_job_runner
from quantinue.orchestration.job_runner import JobRunner

from .test_event_analysis_production_seam import (
    _EmptyDisclosureSource,
    _EmptyNewsSource,
    _event_config,
    _IsolatedSettings,
    _seed_analysis_scope,
)
from .test_event_evidence import _DATABASE_URL, _reset_database


class _Articles:
    def __init__(self, *items: RawNewsWrite) -> None:
        self.items = items

    async def articles(self, session: object, until: object) -> tuple[RawNewsWrite, ...]:
        _ = session, until
        return self.items


class _TickerFailureTransport:
    def __init__(self, failed_ticker: str | None = None) -> None:
        self.failed_ticker = failed_ticker
        self.calls: list[AnalysisTask] = []

    def maximum_usage(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> MaximumTokenUsage:
        _ = task, prompt, profile
        return MaximumTokenUsage(model="transport-double", input_tokens=10, output_tokens=10)

    async def analyze(
        self, task: AnalysisTask, prompt: str, *, profile: str | None = None
    ) -> AnalysisResult:
        _ = profile
        self.calls.append(task)
        if self.failed_ticker is not None and self.failed_ticker in prompt:
            message = f"malformed structured output for {self.failed_ticker}"
            raise RuntimeError(message)
        return AnalysisResult(
            score=0.9,
            label="buy" if task is AnalysisTask.STRATEGY else "approved",
            reason="deterministic",
            bull_case="durable" if task is AnalysisTask.STRATEGY else None,
            key_risk="bounded" if task is AnalysisTask.STRATEGY else None,
            usage=TokenUsage(input_tokens=2, output_tokens=3),
            metadata=AnalysisMetadata(
                model="transport-double",
                provider=ModelProvider.MOCK,
                prompt_version="test-v1",
                policy_version="test-policy",
                input_hash=("a" if task is AnalysisTask.STRATEGY else "b") * 64,
            ),
        )


def _article(identity: int, ticker: str = "AAPL") -> RawNewsWrite:
    return RawNewsWrite(
        article_id=identity,
        ticker=ticker,
        trade_date=datetime(2026, 7, 24, tzinfo=UTC).date(),
        headline=f"{ticker} raises guidance",
        source="Reuters",
        url=f"https://reuters.com/markets/{identity}",
        published_at=datetime(2026, 7, 24, 13, 30, tzinfo=UTC),
    )


async def _runner(
    store: PostgresRunStore,
    transport: _TickerFailureTransport,
    *items: RawNewsWrite,
) -> JobRunner:
    config = _event_config(enabled=True)
    analyzer = BudgetedAnalyzer(
        transport,
        ledger=store.domain,
        daily_limit_usd=config.budget.daily_llm_usd,
        pricing=config.budget.model_pricing,
    )
    runner = build_job_runner(
        _IsolatedSettings(database_url=PostgresDsn(_DATABASE_URL)),
        config,
        store=store,
        sources=JobSources(
            analyzer=analyzer,
            disclosures=_EmptyDisclosureSource(),
            news=_Articles(*items),
            wire_news=_EmptyNewsSource(),
            ownership=object(),
        ),
    )
    assert runner is not None
    return runner


async def _close(runner: JobRunner) -> None:
    runtime = runner.event_runtime
    if runtime is not None:
        await runtime.close()


@pytest.mark.anyio
async def test_event_completion_blocks_price_trigger_until_t31() -> None:
    await _reset_database()
    await _seed_analysis_scope(_DATABASE_URL)
    store = PostgresRunStore(_DATABASE_URL)
    await store.initialize()
    transport = _TickerFailureTransport()
    runner = await _runner(store, transport, _article(8201))
    t0 = datetime(2026, 7, 24, 14, tzinfo=UTC)

    _ = await runner.tick(t0)
    assert not await store.domain.claim_rejudgement(
        "AAPL",
        "aggressive",
        owner_token="price-t10",
        now=t0 + timedelta(minutes=10),
        cooldown=timedelta(minutes=30),
    )
    assert await store.domain.claim_rejudgement(
        "AAPL",
        "aggressive",
        owner_token="price-t31",
        now=t0 + timedelta(minutes=31),
        cooldown=timedelta(minutes=30),
    )

    assert await store.domain.release_rejudgement("AAPL", "aggressive", owner_token="price-t31")
    await _close(runner)
    await store.close()
    assert transport.calls == [AnalysisTask.STRATEGY, AnalysisTask.CRITIC]


@pytest.mark.anyio
async def test_price_completion_blocks_event_trigger_until_t31() -> None:
    await _reset_database()
    await _seed_analysis_scope(_DATABASE_URL)
    store = PostgresRunStore(_DATABASE_URL)
    await store.initialize()
    t0 = datetime(2026, 7, 24, 14, tzinfo=UTC)
    assert await store.domain.claim_rejudgement(
        "AAPL",
        "aggressive",
        owner_token="price-t0",
        now=t0,
        cooldown=timedelta(minutes=30),
    )
    assert await store.domain.complete_rejudgement(
        "AAPL", "aggressive", owner_token="price-t0", now=t0
    )
    transport = _TickerFailureTransport()
    blocked = await _runner(store, transport, _article(8202))
    _ = await blocked.tick(t0 + timedelta(minutes=10))
    await _close(blocked)
    admitted = await _runner(store, transport, _article(8203))
    _ = await admitted.tick(t0 + timedelta(minutes=31))

    await _close(admitted)
    await store.close()
    assert transport.calls == [AnalysisTask.STRATEGY, AnalysisTask.CRITIC]


@pytest.mark.anyio
async def test_mixed_tickers_keep_success_and_failure_durable_per_ticker() -> None:
    await _reset_database()
    await _seed_analysis_scope(_DATABASE_URL)
    engine = create_async_engine(_DATABASE_URL)
    async with engine.begin() as connection:
        _ = await connection.execute(
            text(
                """
                INSERT INTO tb_universe (as_of_date,ticker,company_name,market_cap,listing_status)
                SELECT as_of_date,'MSFT','Microsoft',market_cap,listing_status
                FROM tb_universe WHERE ticker='AAPL'
                ORDER BY as_of_date DESC LIMIT 1
                """
            )
        )
        _ = await connection.execute(
            text(
                """
                INSERT INTO tb_daily_pick
                  (trade_date,ticker,universe_as_of,bucket,rank,sector,score)
                SELECT trade_date,'MSFT',universe_as_of,bucket,rank+1,sector,score
                FROM tb_daily_pick WHERE ticker='AAPL'
                ORDER BY trade_date DESC LIMIT 1
                """
            )
        )
        _ = await connection.execute(
            text(
                """
                INSERT INTO tb_daily_bar (trade_date,ticker,open,high,low,close,volume,source)
                VALUES
                  ('2026-07-22','MSFT',98,101,97,100,1000,'test'),
                  ('2026-07-23','MSFT',100,104,99,103,1200,'test')
                """
            )
        )
    store = PostgresRunStore(_DATABASE_URL)
    await store.initialize()
    transport = _TickerFailureTransport("MSFT")
    runner = await _runner(store, transport, _article(8204), _article(8205, "MSFT"))
    _ = await runner.tick(datetime(2026, 7, 24, 14, tzinfo=UTC))
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT
                      (SELECT count(*) FROM tb_strategist_signals WHERE ticker='AAPL'
                        AND source='event'),
                      (SELECT count(*) FROM tb_critic_verdict WHERE ticker='AAPL'
                        AND source='event'),
                      (SELECT count(*) FROM tb_strategist_signals
                        WHERE ticker='MSFT' AND source='event'),
                      (SELECT count(*) FROM tb_critic_verdict
                        WHERE ticker='MSFT' AND source='event'),
                      (SELECT count(*) FROM tb_event_processing_receipt
                        WHERE ticker='MSFT' AND status='claimed'
                          AND completed_at IS NOT NULL),
                      (SELECT count(*) FROM tb_order)
                    """
                )
            )
        ).one()

    await _close(runner)
    await store.close()
    await engine.dispose()
    assert tuple(row) == (1, 1, 0, 0, 1, 0)

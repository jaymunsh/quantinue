from datetime import UTC, datetime, timedelta
from decimal import Decimal

import anyio
import pytest

from integration.test_event_evidence import (
    _DATABASE_URL,
    _accepted_route,
    _CountingAnalyzer,
    _reset_database,
)
from quantinue.db.domain import PostgresDomainRepository
from quantinue.events.analysis_repository import (
    EventAnalysisReceiptClaim,
    EventAnalysisStage,
    PostgresEventAnalysisReceiptRepository,
)
from quantinue.events.evidence_repository import PostgresEventEvidenceRepository
from quantinue.llm.budget import LlmUsageRecord


@pytest.mark.anyio
async def test_owner_transitions_acknowledge_exact_generation() -> None:
    await _reset_database()
    route = await _accepted_route(
        "owner-machine", '{"headline":"Apple guidance","source":"Reuters"}'
    )
    evidence = PostgresEventEvidenceRepository(_DATABASE_URL)
    pack = await evidence.prepare(route, _CountingAnalyzer())
    receipts = PostgresEventAnalysisReceiptRepository(
        _DATABASE_URL, ownership_ttl=timedelta(seconds=1)
    )
    now = datetime(2026, 7, 24, 14, tzinfo=UTC)
    assert (
        await receipts.claim(
            pack,
            "aggressive",
            EventAnalysisStage.STRATEGIST,
            now,
            timedelta(minutes=30),
            "owner-a",
        )
        is EventAnalysisReceiptClaim.CLAIMED
    )
    assert not await receipts.mark_dispatched(
        route.event_id,
        route.ticker,
        "aggressive",
        EventAnalysisStage.STRATEGIST,
        "owner-b",
    )
    assert (
        await receipts.claim(
            pack,
            "aggressive",
            EventAnalysisStage.STRATEGIST,
            now + timedelta(seconds=2),
            timedelta(minutes=30),
            "owner-b",
        )
        is EventAnalysisReceiptClaim.CLAIMED
    )
    assert not await receipts.release_unbilled(
        route.event_id,
        route.ticker,
        "aggressive",
        EventAnalysisStage.STRATEGIST,
        "owner-a",
    )
    assert await receipts.mark_dispatched(
        route.event_id,
        route.ticker,
        "aggressive",
        EventAnalysisStage.STRATEGIST,
        "owner-b",
    )
    assert not await receipts.mark_dispatched(
        route.event_id,
        route.ticker,
        "aggressive",
        EventAnalysisStage.STRATEGIST,
        "owner-b",
    )
    assert not await receipts.complete(
        route.event_id,
        route.ticker,
        "aggressive",
        EventAnalysisStage.STRATEGIST,
        {"result": {"score": 0}},
        "owner-a",
    )
    assert await receipts.complete(
        route.event_id,
        route.ticker,
        "aggressive",
        EventAnalysisStage.STRATEGIST,
        {"result": {"score": 1}},
        "owner-b",
    )
    await receipts.close()
    await evidence.close()


@pytest.mark.anyio
async def test_two_connections_atomically_admit_one_budget_maximum() -> None:
    await _reset_database()
    first = PostgresDomainRepository(_DATABASE_URL)
    second = PostgresDomainRepository(_DATABASE_URL)
    await first.initialize()
    await second.initialize()
    admitted = []

    async def reserve(repository: PostgresDomainRepository, identity: str) -> None:
        admitted.append(
            await repository.reserve_llm_budget(
                reservation_id=identity,
                owner_token=f"{identity}-owner",
                budget_day=datetime(2026, 7, 24, tzinfo=UTC).date(),
                reserve_class="general",
                max_cost_usd=Decimal("0.75"),
                spending_limit=Decimal("1.00"),
                claimed_at=datetime(2026, 7, 24, tzinfo=UTC),
            )
        )

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(reserve, first, "first")
        tasks.start_soon(reserve, second, "second")
    winners = [reservation for reservation in admitted if reservation is not None]
    assert len(winners) == 1
    winner = winners[0]
    assert await first.dispatch_llm_budget(
        winner, dispatched_at=datetime(2026, 7, 24, 0, 0, 1, tzinfo=UTC)
    )
    assert await first.settle_llm_budget(
        winner,
        LlmUsageRecord(
            called_at=datetime(2026, 7, 24, 0, 0, 2, tzinfo=UTC),
            task="strategy",
            model="test",
            prompt_tokens=1,
            completion_tokens=1,
            est_cost_usd=Decimal("0.50"),
        ),
    )
    assert await first.llm_spend_on(datetime(2026, 7, 24, tzinfo=UTC).date()) == Decimal(
        "0.50"
    )
    await first.close()
    await second.close()

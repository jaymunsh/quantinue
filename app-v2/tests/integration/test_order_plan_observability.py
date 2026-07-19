"""Every role 09 decision is recorded, especially the ones that block a buy.

Until now only orders that actually existed left a row, so a guard that fired
was invisible to SQL — the reason survived only inside a JSONB summary string.
Threshold calibration (`premarket_gap_max` above all) depends on being able to
count how often each guard fired, so the blocks have to be queryable.
"""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from quantinue.db.postgres import PostgresRunStore

from .test_m4_guards_end_to_end import (
    MIDDAY,
    MIDDAY_HALTED,
    PREMARKET,
    _run_guarded_pipeline,
)

DATABASE_URL = os.environ.get("QUANTINUE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(DATABASE_URL is None, reason="requires PostgreSQL")

LATE_ENTRY_AT = datetime(2026, 7, 21, 17, 0, tzinfo=UTC)


async def _plans() -> list[tuple[str, str, str | None, int]]:
    assert DATABASE_URL is not None
    store = PostgresRunStore(DATABASE_URL)
    await store.initialize()
    async with store.engine.begin() as connection:
        rows = await connection.execute(
            text(
                "SELECT ticker, decision, skipped_reason, quantity "
                "FROM tb_order_plan ORDER BY id"
            )
        )
        return [tuple(row) for row in rows]  # type: ignore[misc]


@pytest.mark.anyio
async def test_a_placed_order_is_recorded_as_planned() -> None:
    _ = await _run_guarded_pipeline(MIDDAY)

    planned = [row for row in await _plans() if row[1] == "planned"]

    assert planned
    assert planned[-1][2] is None
    assert planned[-1][3] > 0


@pytest.mark.anyio
async def test_a_gap_block_is_queryable_by_reason() -> None:
    _ = await _run_guarded_pipeline(PREMARKET, current=108.0, close_prev=100.0)

    reasons = [row[2] for row in await _plans() if row[1] == "skipped"]

    assert "premarket_gap" in reasons


@pytest.mark.anyio
async def test_a_late_entry_block_is_queryable_by_reason() -> None:
    _ = await _run_guarded_pipeline(LATE_ENTRY_AT, ret_5d_percent=22.0)

    reasons = [row[2] for row in await _plans() if row[1] == "skipped"]

    assert "late_entry" in reasons


@pytest.mark.anyio
async def test_a_halted_symbol_still_records_the_plan_that_was_approved() -> None:
    # role 09 planned it; role 10 refused to submit. The plan row proves the
    # decision existed, which is what makes the halted skip auditable at all.
    _ = await _run_guarded_pipeline(MIDDAY_HALTED, halted=frozenset({"NVDA"}))

    plans = await _plans()

    assert any(row[1] == "planned" for row in plans)

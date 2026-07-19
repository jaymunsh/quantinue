"""Role 08 must judge on the price role 02 actually observed, never a synthetic one."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quantinue.core.contracts import PriceSnapshot
from quantinue.market_data.models import Candle, Provenance
from quantinue.orchestration.policy import GatesConfig
from quantinue.roles.role_02_technical_analysis.service import price_snapshot_from

NOW = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
GATES = GatesConfig()


def _candle(close: str, high: str, low: str, day: int) -> Candle:
    return Candle(
        ticker="NVDA",
        opened_at=NOW - timedelta(days=day),
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=1_000_000,
        provenance=Provenance(
            source="nasdaq-historical",
            source_ref="https://example.test/historical",
            observed_at=NOW,
            captured_at=NOW,
            confidence=1.0,
            execution_id="run",
        ),
    )


def test_snapshot_carries_the_real_previous_close() -> None:
    candles = (_candle("100", "101", "99", 1), _candle("110", "115", "105", 0))

    snapshot = price_snapshot_from(candles)

    assert snapshot is not None
    assert snapshot.current_price == 110.0
    assert snapshot.day_high == 115.0
    assert snapshot.day_low == 105.0
    # 합성이면 close_prev == current_price가 되어 급등 가드가 무력화된다.
    assert snapshot.close_prev == 100.0
    assert snapshot.close_prev != snapshot.current_price


def test_snapshot_needs_two_sessions_to_know_a_previous_close() -> None:
    assert price_snapshot_from((_candle("100", "101", "99", 0),)) is None
    assert price_snapshot_from(()) is None


def test_snapshot_drift_within_tolerance_is_accepted() -> None:
    snapshot = PriceSnapshot(current_price=100.0, day_high=101.0, day_low=99.0, close_prev=98.0)

    assert snapshot.drift_from(101.9) <= GATES.snapshot_tolerance
    assert snapshot.is_stale(101.9, GATES.snapshot_tolerance) is False


def test_snapshot_drift_beyond_tolerance_is_stale() -> None:
    snapshot = PriceSnapshot(current_price=100.0, day_high=101.0, day_low=99.0, close_prev=98.0)

    # 2% 허용오차: 102.01은 초과.
    assert snapshot.is_stale(102.01, GATES.snapshot_tolerance) is True
    assert snapshot.is_stale(97.9, GATES.snapshot_tolerance) is True


def test_snapshot_tolerance_boundary_is_exact() -> None:
    snapshot = PriceSnapshot(current_price=100.0, day_high=101.0, day_low=99.0, close_prev=98.0)

    assert snapshot.is_stale(102.0, 0.02) is False
    assert snapshot.is_stale(98.0, 0.02) is False

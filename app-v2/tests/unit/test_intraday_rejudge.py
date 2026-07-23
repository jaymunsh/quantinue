from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from quantinue.orchestration.intraday_rejudge import IntradayRejudgeEngine
from quantinue.orchestration.work_lease import WorkLease
from quantinue.roles.analysis.job import AnalysisRun


class _Domain:
    async def claim_rejudgement(
        self,
        ticker: str,
        persona: str,
        *,
        owner_token: str,
        now: datetime,
        cooldown: timedelta,
    ) -> bool:
        _ = ticker, persona, owner_token, now, cooldown
        return True

    async def complete_rejudgement(
        self,
        ticker: str,
        persona: str,
        *,
        owner_token: str,
        now: datetime,
    ) -> bool:
        _ = ticker, persona, owner_token, now
        return True

    async def release_rejudgement(
        self, ticker: str, persona: str, *, owner_token: str
    ) -> bool:
        _ = ticker, persona, owner_token
        return True

    async def approved_sell_profiles(
        self, as_of: date, tickers: tuple[str, ...]
    ) -> dict[str, frozenset[str]]:
        _ = (as_of, tickers)
        return {}


class _Job:
    def __init__(self, skipped: int) -> None:
        self.skipped = skipped
        self.profile_name = f"profile-{skipped}"

    async def run_intraday(
        self,
        *,
        now: datetime,
        prices: dict[str, Decimal],
        lease: WorkLease | None = None,
    ) -> AnalysisRun:
        _ = (now, prices, lease)
        return AnalysisRun((), self.skipped)


class _Exits:
    async def run_soft_sells(
        self,
        *,
        as_of: date,
        prices: dict[str, Decimal],
        profiles: dict[str, frozenset[str]],
    ) -> tuple[()]:
        _ = (as_of, prices, profiles)
        return ()


@pytest.mark.anyio
async def test_partial_persona_result_fails_the_sweep_for_retry() -> None:
    # Given
    engine = IntradayRejudgeEngine(
        domain=_Domain(), jobs=(_Job(0), _Job(1)), exits=_Exits()
    )

    # When / Then
    with pytest.raises(RuntimeError, match="skipped=1"):
        await engine.run(
            now=datetime(2026, 7, 20, 14, 1, tzinfo=UTC),
            prices={"NVDA": Decimal(100)},
        )

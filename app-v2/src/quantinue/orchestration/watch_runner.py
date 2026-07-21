"""Regular-session gate and loop for intraday position watching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

import anyio
import structlog

from quantinue.core.market_calendar import NyseCalendar

if TYPE_CHECKING:
    from quantinue.orchestration.policy import WatchConfig


@dataclass(frozen=True, slots=True)
class WatchOutcome:
    """One observable result from an intraday watch tick."""

    reason: Literal["disabled", "market_closed", "ready"]


class WatchRunner:
    """Wake during the regular session without touching the daily-job ledger."""

    def __init__(
        self,
        config: WatchConfig,
        calendar: NyseCalendar | None = None,
    ) -> None:
        """Bind the watch policy to the shared NYSE calendar adapter."""
        self._config = config
        self._calendar = calendar or NyseCalendar()
        self._logger: structlog.stdlib.BoundLogger = structlog.get_logger("watch")

    async def tick(self, now: datetime) -> WatchOutcome:
        """Apply the switch and session gate; later milestones add watch work."""
        if not self._config.enabled:
            return WatchOutcome("disabled")
        if not self._calendar.is_market_open(now):
            return WatchOutcome("market_closed")
        return WatchOutcome("ready")

    async def run_forever(self) -> None:
        """Tick forever while isolating failures from the application lifespan."""
        while True:
            try:
                outcome = await self.tick(datetime.now(UTC))
                if outcome.reason == "ready":
                    await self._logger.ainfo("watch.tick", reason=outcome.reason)
            except Exception:  # noqa: BLE001 - 한 틱 실패가 다음 감시 기회를 없애면 안 된다.
                await self._logger.aexception("watch.tick.failed")
            await anyio.sleep(self._config.interval_minutes * 60)

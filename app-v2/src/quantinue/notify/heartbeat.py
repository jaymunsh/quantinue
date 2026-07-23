"""External dead-man heartbeat for the sole observation owner."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Protocol

import anyio
import httpx2
from sqlalchemy.exc import SQLAlchemyError
from structlog.stdlib import BoundLogger, get_logger

from quantinue.core.market_calendar import NEW_YORK
from quantinue.runtime_status import RuntimeSnapshot, present_runtime

_logger: BoundLogger = get_logger("heartbeat")

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import date

    from quantinue.core.config import Settings
    from quantinue.db.control_room_reads import JobRunRecord

_TIMEOUT: Final = httpx2.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)
_LIMITS: Final = httpx2.Limits(
    max_connections=10,
    max_keepalive_connections=5,
    keepalive_expiry=30.0,
)
_SOCKET_OPTIONS: Final = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]


class HeartbeatSender(Protocol):
    """Small outbound boundary that keeps reporter tests off implementation details."""

    async def get(self, url: str) -> None:
        """Deliver one success or failure signal."""
        ...


class JobRunReader(Protocol):
    """Read enough durable state to prove the database remains reachable."""

    async def job_runs(self, slot_date: date) -> tuple[JobRunRecord, ...]:
        """Return the selected slot's durable job rows."""
        ...


class HttpHeartbeatSender:
    """Send a token-bearing heartbeat without ever logging its URL."""

    async def get(self, url: str) -> None:
        """Deliver one signal through a bounded, retrying HTTP client."""
        transport = httpx2.AsyncHTTPTransport(
            http2=True,
            retries=3,
            limits=_LIMITS,
            socket_options=_SOCKET_OPTIONS,
        )
        async with httpx2.AsyncClient(
            transport=transport,
            timeout=_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            _ = response.raise_for_status()


@dataclass(frozen=True, slots=True)
class RuntimeHealthProbe:
    """Combine durable database reachability with process-local worker liveness."""

    job_runs: JobRunReader
    snapshot: Callable[[], RuntimeSnapshot]
    daily_attached: bool

    async def __call__(self) -> bool:
        """Return whether the external dead-man signal may report success."""
        now = datetime.now(UTC)
        try:
            _ = await self.job_runs.job_runs(now.astimezone(NEW_YORK).date())
        except SQLAlchemyError:
            return False
        runtime = self.snapshot().model_copy(
            update={"daily_attached": self.daily_attached}
        )
        view = present_runtime(runtime, now=now)
        return view.watch_status not in {"off", "attention"}


@dataclass(frozen=True, slots=True)
class HeartbeatReporter:
    """Report operational health until the application lifespan cancels it."""

    ping_url: str
    probe: Callable[[], Awaitable[bool]]
    sender: HeartbeatSender
    interval_seconds: float

    async def report_once(self) -> None:
        """Send the probe's current state once."""
        is_healthy = await self.probe()
        await self.sender.get(self.ping_url if is_healthy else f"{self.ping_url}/fail")

    async def run_forever(self) -> None:
        """Report until the owning application lifespan cancels this task."""
        while True:
            try:
                await self.report_once()
            except httpx2.HTTPError as error:
                await _logger.awarning(
                    "heartbeat.send.failed", reason=type(error).__name__
                )
            await anyio.sleep(self.interval_seconds)


def build_heartbeat_reporter(
    settings: Settings, probe: RuntimeHealthProbe
) -> HeartbeatReporter | None:
    """Build the owner-only reporter when a secret ping URL is configured."""
    if not settings.background_workers or settings.heartbeat_url is None:
        return None
    return HeartbeatReporter(
        ping_url=settings.heartbeat_url.get_secret_value().rstrip("/"),
        probe=probe,
        sender=HttpHeartbeatSender(),
        interval_seconds=300,
    )

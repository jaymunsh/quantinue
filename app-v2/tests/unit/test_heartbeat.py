from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import ClassVar

import anyio
import httpx2
import pytest
from anyio.lowlevel import checkpoint
from typing_extensions import override

from quantinue.notify.heartbeat import HeartbeatReporter, HttpHeartbeatSender


class _ReceiptHandler(BaseHTTPRequestHandler):
    receipts: ClassVar[list[tuple[str, str]]] = []

    def do_GET(self) -> None:
        self.receipts.append((self.command, self.path))
        self.send_response(200)
        self.end_headers()

    @override
    def log_message(self, format: str, *args: object) -> None:
        del format, args


@dataclass(slots=True)
class _RecordingSender:
    urls: list[str] = field(default_factory=list)

    async def get(self, url: str) -> None:
        self.urls.append(url)


@pytest.mark.anyio
async def test_reporter_sends_success_when_runtime_probe_is_healthy() -> None:
    # Given
    sender = _RecordingSender()

    async def healthy() -> bool:
        return True

    reporter = HeartbeatReporter(
        ping_url="https://hc-ping.com/test-check",
        probe=healthy,
        sender=sender,
        interval_seconds=300,
    )

    # When
    await reporter.report_once()

    # Then
    assert sender.urls == ["https://hc-ping.com/test-check"]


@pytest.mark.anyio
async def test_reporter_sends_failure_when_runtime_probe_is_degraded() -> None:
    # Given
    sender = _RecordingSender()

    async def degraded() -> bool:
        return False

    reporter = HeartbeatReporter(
        ping_url="https://hc-ping.com/test-check",
        probe=degraded,
        sender=sender,
        interval_seconds=300,
    )

    # When
    await reporter.report_once()

    # Then
    assert sender.urls == ["https://hc-ping.com/test-check/fail"]


@pytest.mark.anyio
async def test_http_sender_delivers_exact_success_and_failure_wire_paths() -> None:
    # Given
    _ReceiptHandler.receipts = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ReceiptHandler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/synthetic-check"
    sender = HttpHeartbeatSender()

    # When
    try:
        await sender.get(base_url)
        await sender.get(f"{base_url}/fail")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)

    # Then
    assert _ReceiptHandler.receipts == [
        ("GET", "/synthetic-check"),
        ("GET", "/synthetic-check/fail"),
    ]


@pytest.mark.anyio
async def test_network_failures_are_sanitized_and_recovery_keeps_loop_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    attempts: list[str] = []
    events: list[tuple[str, dict[str, str]]] = []

    @dataclass(slots=True)
    class _RecoveringSender:
        async def get(self, url: str) -> None:
            attempts.append(url)
            if len(attempts) < 3:
                request = httpx2.Request("GET", url)
                message = "token=do-not-log"
                if len(attempts) == 1:
                    raise httpx2.ConnectError(message, request=request)
                raise httpx2.ReadTimeout(message, request=request)
            raise anyio.get_cancelled_exc_class()

    async def capture(event: str, **fields: str) -> None:
        events.append((event, fields))

    monkeypatch.setattr("quantinue.notify.heartbeat._logger.awarning", capture)

    async def healthy() -> bool:
        return True

    reporter = HeartbeatReporter(
        ping_url="https://hc-ping.com/00000000-0000-4000-8000-000000000099",
        probe=healthy,
        sender=_RecoveringSender(),
        interval_seconds=0,
    )

    # When / Then
    with pytest.raises(anyio.get_cancelled_exc_class()):
        await reporter.run_forever()
    assert len(attempts) == 3
    assert events == [
        ("heartbeat.send.failed", {"reason": "ConnectError"}),
        ("heartbeat.send.failed", {"reason": "ReadTimeout"}),
    ]
    assert "00000000-0000-4000-8000-000000000099" not in repr(events)
    assert "do-not-log" not in repr(events)


@pytest.mark.anyio
async def test_probe_failure_is_sanitized_and_next_iteration_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    events: list[tuple[str, dict[str, str]]] = []
    probe_calls = 0
    sender = _RecordingSender()

    async def capture(event: str, **fields: str) -> None:
        events.append((event, fields))

    async def fails_once() -> bool:
        nonlocal probe_calls
        probe_calls += 1
        if probe_calls == 1:
            message = "synthetic-secret-must-not-escape"
            raise RuntimeError(message)
        return True

    monkeypatch.setattr("quantinue.notify.heartbeat._logger.awarning", capture)
    reporter = HeartbeatReporter(
        ping_url="https://hc-ping.com/00000000-0000-4000-8000-000000000088",
        probe=fails_once,
        sender=sender,
        interval_seconds=0,
    )

    # When
    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(reporter.run_forever)
        while not sender.urls:
            await checkpoint()
        task_group.cancel_scope.cancel()

    # Then
    assert sender.urls == [
        "https://hc-ping.com/00000000-0000-4000-8000-000000000088"
    ]
    assert events == [
        ("heartbeat.iteration.failed", {"reason": "RuntimeError"})
    ]
    assert "synthetic-secret-must-not-escape" not in repr(events)
    assert "00000000-0000-4000-8000-000000000088" not in repr(events)


@pytest.mark.anyio
async def test_reporter_loop_stops_cleanly_when_application_is_cancelled() -> None:
    # Given
    sender = _RecordingSender()

    async def healthy() -> bool:
        return True

    reporter = HeartbeatReporter(
        ping_url="https://hc-ping.com/test-check",
        probe=healthy,
        sender=sender,
        interval_seconds=300,
    )

    # When
    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(reporter.run_forever)
        await checkpoint()
        task_group.cancel_scope.cancel()

    # Then
    assert sender.urls == ["https://hc-ping.com/test-check"]

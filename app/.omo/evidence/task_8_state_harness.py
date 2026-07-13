# ruff: noqa: INP001
"""Store-backed visual state harness for the server-rendered control room."""

from datetime import UTC, datetime
from os import environ

from typing_extensions import override

from quantinue.core.contracts import PipelineRun, RunId, RunStatus
from quantinue.core.ontology import StageAttemptState
from quantinue.db.contracts import PersistedAttempt
from quantinue.db.memory import InMemoryRunStore
from quantinue.main import create_app


class HarnessStore(InMemoryRunStore):
    """Expose one actual persisted run/attempt through the normal Store protocol."""

    def __init__(self, run: PipelineRun, attempt: PersistedAttempt) -> None:
        """Bind one run and attempt snapshot."""
        super().__init__()
        self._harness_run = run
        self._harness_attempt = attempt

    @override
    async def list_recent(self, limit: int = 20) -> tuple[PipelineRun, ...]:
        """Return the seeded run through the normal query."""
        return (self._harness_run,)[:limit]

    @override
    async def list_attempts(self, run_id: RunId) -> tuple[PersistedAttempt, ...]:
        """Return the seeded attempt for its run."""
        return (self._harness_attempt,) if run_id == self._harness_run.run_id else ()


state = StageAttemptState(environ.get("QUANTINUE_HARNESS_STATE", "running"))
now = datetime(2026, 7, 13, 6, 0, tzinfo=UTC)
failure_code = (
    "ROLE_TIMEOUT"
    if state is StageAttemptState.TIMED_OUT
    else "ProviderTimeout"
    if state in {StageAttemptState.RETRYING, StageAttemptState.FAILED}
    else None
)
run_status = RunStatus.COMPLETED if state is StageAttemptState.TIMED_OUT else RunStatus(state.value)
run = PipelineRun(
    run_id=RunId(f"harness-{state.value}"),
    ticker="NVDA",
    cycle_ts=now,
    status=run_status,
    stages=(),
    evidence_trace=(),
)
attempt = PersistedAttempt(
    component="01",
    attempt_no=2 if state is StageAttemptState.RETRYING else 1,
    status=state.value,
    started_at=now,
    finished_at=now if state in {StageAttemptState.FAILED, StageAttemptState.TIMED_OUT} else None,
    error_code=failure_code,
    error_message="raw provider response",
)

app = create_app(store=HarnessStore(run, attempt))

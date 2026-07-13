from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from typing_extensions import override

from quantinue.api.presentation import control_room_run
from quantinue.api.schemas import ControlRoomRun
from quantinue.core.contracts import (
    PipelineRun,
    RoleEvidenceTrace,
    RunId,
    RunStatus,
    StageResult,
    StageStatus,
)
from quantinue.core.terminal_run_types import OrderResult, ReviewResult
from quantinue.db.contracts import PersistedAttempt
from quantinue.db.memory import InMemoryRunStore
from quantinue.main import create_app


class StateRunStore(InMemoryRunStore):
    """Store-protocol fixture whose API and UI read the same persisted snapshot."""

    def __init__(self, run: PipelineRun, attempt: PersistedAttempt) -> None:
        super().__init__()
        self._state_run = run
        self._state_attempt = attempt

    @override
    async def list_recent(self, limit: int = 20) -> tuple[PipelineRun, ...]:
        return (self._state_run,)[:limit]

    @override
    async def list_attempts(self, run_id: RunId) -> tuple[PersistedAttempt, ...]:
        return (self._state_attempt,) if run_id == self._state_run.run_id else ()


def test_dashboard_runs_and_displays_pipeline() -> None:
    # Given
    app = create_app()

    # When
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"ticker": "NVDA"})
        created = PipelineRun.model_validate_json(response.content)
        observability = client.get(f"/api/runs/{created.run_id}")
        dashboard = client.get("/")

    # Then
    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert observability.status_code == 200
    payload = ControlRoomRun.model_validate_json(observability.content)
    assert payload.run_id == created.run_id
    assert len(payload.stages) == 11
    assert payload.stages[0].attempts[0].attempt_no == 1
    assert payload.stages[0].checkpointed is True
    assert payload.evidence[0].confidence == 1.0
    assert payload.evidence[4].model_name == "deterministic-mock-v1"
    assert payload.evidence[4].model_provider == "mock"
    assert len(payload.evidence[4].input_hash or "") == 64
    assert "error_message" not in observability.text
    assert dashboard.status_code == 200
    assert "NVDA" in dashboard.text
    assert "11 / 11" in dashboard.text
    assert "근거 계보" in dashboard.text
    assert "중복 방지 ID" in dashboard.text
    assert "T+5 리뷰" in dashboard.text
    assert "deterministic-mock-v1" in dashboard.text
    assert "UNTRUSTED_EXTERNAL_DATA" not in dashboard.text


def test_health_reports_safe_default_modes() -> None:
    # Given
    app = create_app()

    # When
    with TestClient(app) as client:
        response = client.get("/health")

    # Then
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "broker_mode": "mock", "llm_mode": "mock"}


def test_invalid_form_ticker_returns_to_control_room_with_an_accessible_error() -> None:
    # Given
    app = create_app()

    # When
    with TestClient(app) as client:
        invalid = client.post("/runs", data={"ticker": "BAD!"}, follow_redirects=False)
        dashboard = client.get(invalid.headers["location"])

    # Then
    assert invalid.status_code == 303
    assert invalid.headers["location"] == "/?error=invalid_ticker"
    assert dashboard.status_code == 200
    assert 'role="alert"' in dashboard.text
    assert "티커 형식을 확인하세요" in dashboard.text


def test_control_room_view_exposes_states_timing_lineage_and_redacts_failure() -> None:
    started = datetime(2026, 7, 13, 1, 0, tzinfo=UTC)
    run = PipelineRun(
        run_id=RunId("run-safe"),
        ticker="NVDA",
        cycle_ts=started,
        status=RunStatus.FAILED,
        stages=(
            StageResult(
                component="01",
                name="Universe Screener",
                status=StageStatus.COMPLETED,
                summary="fixture universe",
            ),
        ),
        evidence_trace=(
            RoleEvidenceTrace(
                run_id=RunId("run-safe"),
                evidence_id="evidence-01",
                parent_evidence_ids=("root-evidence",),
                component="01",
                source="fixture",
                source_ref="fixture://market/NVDA",
                observed_at=started,
                captured_at=started + timedelta(seconds=1),
                confidence=0.875,
            ),
        ),
        order=OrderResult(
            order_id="mock-order-safe",
            client_order_id="run-safe-10",
            status="reconciled",
            quantity=1,
            filled_avg_price=123.45,
        ),
        review=ReviewResult(outcome="hit", summary="T+5 positive"),
    )
    attempts = (
        PersistedAttempt(
            component="01",
            attempt_no=1,
            status="completed",
            started_at=started,
            finished_at=started + timedelta(milliseconds=250),
        ),
        PersistedAttempt(
            component="02",
            attempt_no=2,
            status="retrying",
            started_at=started + timedelta(seconds=1),
            error_code="ProviderTimeout",
            error_message="secret-token raw provider response",
        ),
    )

    view = control_room_run(run, attempts)

    assert isinstance(view, ControlRoomRun)
    assert view.status == RunStatus.FAILED
    assert view.stages[0].duration_ms == 250
    assert view.stages[1].status == "retrying"
    assert view.stages[1].failure_code == "ProviderTimeout"
    assert "secret-token" not in view.model_dump_json()
    assert view.evidence[0].parent_evidence_ids == ("root-evidence",)
    assert view.order is not None
    assert view.order.client_order_id == "run-safe-10"
    assert view.order.reconciliation_status == "reconciled"
    assert view.review is not None
    assert view.review.outcome == "hit"


def test_empty_dashboard_has_accessible_operational_landmarks() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert 'href="#main"' in response.text
    assert 'aria-label="현재 안전 모드"' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'class="table-wrap" tabindex' not in response.text
    assert '<link rel="stylesheet"' not in response.text
    assert "--bg: #f6f8fa" in response.text
    assert "첫 실행을 기다리고 있습니다" in response.text
    assert "계정 없이 전체 계약을 검증합니다." in response.text
    assert 'class="safety-promise"' in response.text
    expected_contract_copy = "각 역할은 같은 계약 아래 독립적으로 교체됩니다."
    assert expected_contract_copy in response.text


def test_timed_out_attempt_projects_as_safe_failed_stage() -> None:
    now = datetime(2026, 7, 13, 6, 0, tzinfo=UTC)
    run = PipelineRun(
        run_id=RunId("timed-out-run"),
        ticker="NVDA",
        cycle_ts=now,
        status=RunStatus.COMPLETED,
        stages=(
            StageResult(
                component="01",
                name="Universe Screener",
                status=StageStatus.COMPLETED,
                summary="checkpoint complete",
            ),
        ),
    )
    attempt = PersistedAttempt(
        component="01",
        attempt_no=2,
        status="timed_out",
        started_at=now,
        finished_at=now + timedelta(seconds=1),
        error_code="ROLE_TIMEOUT",
        error_message="secret timeout payload",
    )
    app = create_app(store=StateRunStore(run, attempt))

    with TestClient(app) as client:
        dashboard = client.get("/")
        detail = client.get("/api/runs/timed-out-run")

    assert dashboard.status_code == 200
    assert detail.status_code == 200
    assert 'status-failed">failed' in dashboard.text
    assert "timed_out" in dashboard.text
    assert "ROLE_TIMEOUT" in dashboard.text
    assert "secret timeout payload" not in dashboard.text
    assert detail.json()["stages"][0]["status"] == "failed"
    assert detail.json()["stages"][0]["attempts"][0]["status"] == "timed_out"


@pytest.mark.parametrize("run_status", [RunStatus.RUNNING, RunStatus.RETRYING, RunStatus.FAILED])
def test_dashboard_fixture_renders_redacted_nonterminal_states(run_status: RunStatus) -> None:
    now = datetime(2026, 7, 13, 6, 0, tzinfo=UTC)
    stage_status = StageStatus(run_status.value)
    run = PipelineRun(
        run_id=RunId(f"state-{run_status.value}"),
        ticker="NVDA",
        cycle_ts=now,
        status=run_status,
        stages=(),
        evidence_trace=(),
        conviction=None,
        side=None,
        order=None,
        review=None,
    )
    failure_code = None if run_status is RunStatus.RUNNING else "ProviderTimeout"
    attempt = PersistedAttempt(
        component="01",
        attempt_no=1,
        status=stage_status.value,
        started_at=now,
        error_code=failure_code,
        error_message="raw provider response",
    )
    app = create_app(store=StateRunStore(run, attempt))

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert f"status-{run_status.value}" in response.text
    if run_status is RunStatus.RUNNING:
        assert "ProviderTimeout" not in response.text
    else:
        assert "ProviderTimeout" in response.text
    assert "raw provider response" not in response.text

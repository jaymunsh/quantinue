from datetime import UTC, datetime

from fastapi.testclient import TestClient
from typing_extensions import override

from quantinue.core.contracts import PipelineRun, RunId, RunStatus
from quantinue.core.terminal_detail import (
    CollectionFact,
    CriticDetail,
    StrategyDetail,
    TerminalRunDetail,
)
from quantinue.db.contracts import PersistedAttempt
from quantinue.db.memory import InMemoryRunStore
from quantinue.main import create_app


class DetailRunStore(InMemoryRunStore):
    def __init__(self, run: PipelineRun, attempt: PersistedAttempt) -> None:
        super().__init__()
        self._run = run
        self._attempt = attempt

    @override
    async def list_recent(self, limit: int = 20) -> tuple[PipelineRun, ...]:
        return (self._run,)[:limit]

    @override
    async def list_attempts(self, run_id: RunId) -> tuple[PersistedAttempt, ...]:
        return (self._attempt,) if run_id == self._run.run_id else ()


def test_dashboard_renders_safe_collection_to_critic_brief() -> None:
    # Given
    started = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
    run = PipelineRun(
        run_id=RunId("detail-brief"),
        ticker="NVDA",
        cycle_ts=started,
        status=RunStatus.COMPLETED,
        stages=(),
        detail=TerminalRunDetail(
            disclosure=CollectionFact(
                title="10-Q filing",
                summary="Revenue increased year over year.",
                source="SEC EDGAR",
                reference="https://www.sec.gov/Archives/edgar/data/1",
                score=0.82,
            ),
            news=CollectionFact(
                title="Market update",
                summary="Demand remained steady.",
                source="Wire",
                reference="fixture://news/NVDA",
                score=0.71,
            ),
            strategy=StrategyDetail(
                proposal="buy",
                rationale="The setup meets the quality threshold.",
                gate="passed",
                blockers=("position limit",),
                conviction=0.78,
            ),
            critic=CriticDetail(
                verdict="pass",
                rationale="No hard risk gate triggered.",
                layer="risk_review",
            ),
        ),
    )
    app = create_app(store=DetailRunStore(run, _attempt("completed", started)))

    # When
    with TestClient(app) as client:
        response = client.get("/")

    # Then
    assert response.status_code == 200
    assert "수집부터 비평까지" in response.text
    assert "10-Q filing" in response.text
    assert "Market update" in response.text
    assert "전략가 제안" in response.text
    assert "비평가 판정" in response.text
    assert "82.0%" in response.text
    assert "71.0%" in response.text
    assert 'href="https://www.sec.gov/Archives/edgar/data/1"' in response.text
    assert 'target="_blank"' in response.text
    assert 'rel="noopener noreferrer"' in response.text
    assert "fixture://news/NVDA" in response.text
    assert 'href="fixture://news/NVDA"' not in response.text


def test_dashboard_marks_legacy_detail_as_unavailable() -> None:
    # Given
    started = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
    run = PipelineRun(
        run_id=RunId("legacy-detail"),
        ticker="NVDA",
        cycle_ts=started,
        status=RunStatus.FAILED,
        stages=(),
    )
    app = create_app(store=DetailRunStore(run, _attempt("failed", started)))

    # When
    with TestClient(app) as client:
        response = client.get("/")

    # Then
    assert response.status_code == 200
    assert "표시 가능한 수집·판단 정보가 없습니다" in response.text
    assert "failed 상태" in response.text


def _attempt(status: str, started_at: datetime) -> PersistedAttempt:
    return PersistedAttempt(component="01", attempt_no=1, status=status, started_at=started_at)

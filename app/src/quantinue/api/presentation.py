"""Redacted projection helpers shared by control-room HTTP surfaces."""

from typing import Final
from urllib.parse import urlsplit, urlunsplit

from quantinue.api.live_progress import (
    STAGE_NAME_BY_COMPONENT,
    live_stage_views,
    ui_stage_status,
)
from quantinue.api.schemas import (
    AttemptView,
    CollectionDetailView,
    ControlRoomRun,
    CriticDetailView,
    EvidenceView,
    OrderView,
    ReviewView,
    SourceReferenceView,
    StageView,
    StrategyDetailView,
    TerminalRunDetailView,
)
from quantinue.core.contracts import PipelineRun, StageStatus
from quantinue.core.terminal_detail import CollectionFact, TerminalRunDetail
from quantinue.db.contracts import PersistedAttempt

ASCII_CONTROL_LIMIT: Final = 32


def attempt_view(attempt: PersistedAttempt) -> AttemptView:
    """Project a persisted attempt without its raw error message."""
    duration_ms = None
    if attempt.finished_at is not None:
        elapsed = (attempt.finished_at - attempt.started_at).total_seconds()
        duration_ms = max(0, round(elapsed * 1000))
    return AttemptView(
        attempt_no=attempt.attempt_no,
        status=attempt.status,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        duration_ms=duration_ms,
        failure_code=attempt.error_code,
    )


def source_reference_view(reference: str) -> SourceReferenceView:
    """Allow only credential-free absolute HTTP(S) references to be browser links."""
    if any(character.isspace() or ord(character) < ASCII_CONTROL_LIMIT for character in reference):
        return SourceReferenceView(label="invalid reference")
    try:
        parsed = urlsplit(reference)
        _ = parsed.port
    except ValueError:
        return SourceReferenceView(label="invalid reference")
    is_web = parsed.scheme.lower() in {"http", "https"}
    has_credentials = parsed.username is not None or parsed.password is not None
    has_host = parsed.hostname is not None
    if is_web and has_host and not has_credentials:
        label = reference
        href = reference
    elif is_web and has_host and has_credentials:
        safe_port = f":{parsed.port}" if parsed.port is not None else ""
        label = urlunsplit((parsed.scheme, f"{parsed.hostname}{safe_port}", parsed.path, "", ""))
        href = None
    elif parsed.scheme.lower() in {"data", "javascript"}:
        label = "non-web reference"
        href = None
    elif is_web and not has_host:
        label = "invalid reference"
        href = None
    else:
        label = reference
        href = None
    return SourceReferenceView(label=label, href=href)


def _collection_detail_view(fact: CollectionFact) -> CollectionDetailView:
    """Project one already-bounded collection fact into its API representation."""
    return CollectionDetailView(
        title=fact.title,
        summary=fact.summary,
        source=fact.source,
        reference=source_reference_view(fact.reference),
        score=fact.score,
    )


def terminal_run_detail_view(detail: TerminalRunDetail) -> TerminalRunDetailView:
    """Project bounded terminal detail without adding raw execution material."""
    return TerminalRunDetailView(
        disclosure=_collection_detail_view(detail.disclosure),
        news=_collection_detail_view(detail.news),
        strategy=StrategyDetailView(
            proposal=detail.strategy.proposal,
            rationale=detail.strategy.rationale,
            gate=detail.strategy.gate,
            blockers=detail.strategy.blockers,
            conviction=detail.strategy.conviction,
        ),
        critic=CriticDetailView(
            verdict=detail.critic.verdict,
            rationale=detail.critic.rationale,
            layer=detail.critic.layer,
        ),
    )


def control_room_run(run: PipelineRun, attempts: tuple[PersistedAttempt, ...]) -> ControlRoomRun:
    """Build the shared, redacted API and server-rendered observability view."""
    attempts_by_component: dict[str, list[PersistedAttempt]] = {}
    for attempt in attempts:
        attempts_by_component.setdefault(attempt.component, []).append(attempt)
    results_by_component = {stage.component: stage for stage in run.stages}
    components = tuple(dict.fromkeys((*results_by_component, *attempts_by_component)))
    stage_views: list[StageView] = []
    for component in components:
        result = results_by_component.get(component)
        component_attempts = tuple(
            attempt_view(attempt) for attempt in attempts_by_component.get(component, [])
        )
        latest_attempt = component_attempts[-1] if component_attempts else None
        stage_status = result.status if result is not None else StageStatus.PENDING
        if latest_attempt is not None and latest_attempt.status != "completed":
            stage_status = ui_stage_status(latest_attempt.status)
        stage_views.append(
            StageView(
                component=component,
                name=result.name
                if result is not None
                else STAGE_NAME_BY_COMPONENT.get(component, f"Stage {component}"),
                status=stage_status,
                summary=result.summary if result is not None else "완료 전 실행 관측",
                attempts=component_attempts,
                duration_ms=sum(attempt.duration_ms or 0 for attempt in component_attempts) or None,
                checkpointed=result is not None and result.status is StageStatus.COMPLETED,
                failure_code=latest_attempt.failure_code if latest_attempt is not None else None,
            )
        )
    evidence = tuple(
        EvidenceView(
            evidence_id=item.evidence_id,
            component=item.component,
            source=item.source,
            source_ref=item.source_ref,
            observed_at=item.observed_at,
            captured_at=item.captured_at,
            confidence=item.confidence,
            parent_evidence_ids=item.parent_evidence_ids,
            model_name=item.model_name,
            model_provider=item.model_provider,
            prompt_version=item.prompt_version,
            policy_version=item.policy_version,
            input_hash=item.input_hash,
        )
        for item in run.evidence_trace
    )
    order = (
        OrderView(
            order_id=run.order.order_id,
            client_order_id=run.order.client_order_id,
            reconciliation_status=run.order.status,
            quantity=run.order.quantity,
            filled_avg_price=run.order.filled_avg_price,
        )
        if run.order is not None
        else None
    )
    review = (
        ReviewView(outcome=run.review.outcome, summary=run.review.summary)
        if run.review is not None
        else None
    )
    current_stage, next_stage = live_stage_views(run, attempts)
    return ControlRoomRun(
        run_id=run.run_id,
        ticker=run.ticker,
        cycle_ts=run.cycle_ts,
        status=run.status,
        progress=len(run.stages),
        current_stage=current_stage,
        next_stage=next_stage,
        stages=tuple(stage_views),
        evidence=evidence,
        conviction=run.conviction,
        side=run.side,
        detail=terminal_run_detail_view(run.detail),
        order=order,
        review=review,
    )

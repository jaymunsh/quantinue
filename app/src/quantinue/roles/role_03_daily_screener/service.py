"""Select today's candidates from the technical universe."""

from dataclasses import replace
from typing import ClassVar, Final

from quantinue.core.contracts import PipelineContext
from quantinue.core.ontology import Bucket, EvidenceKind
from quantinue.core.schemas import Evidence
from quantinue.core.typing import require_value
from quantinue.roles.role_03_daily_screener.contracts import (
    DailyPick,
    DailyScreenerInput,
    DailyScreenerOutput,
)

DAILY_PICK_THRESHOLD: Final = 0.70


class DailyScreener:
    """MVP bucket gate for one ticker."""

    component: ClassVar[str] = "03"
    name: ClassVar[str] = "2차 스크리너"

    def fixture(self, context: PipelineContext) -> DailyScreenerOutput:
        """Build the deterministic daily-pick row after the score gate."""
        source = Evidence(
            evidence_id=f"{context.run_id}:03:screen",
            run_id=context.run_id,
            source="fixture",
            source_ref=f"fixture://daily-pick/{context.request.ticker}",
            observed_at=context.request.cycle_ts,
            captured_at=context.request.cycle_ts,
            confidence=1.0,
            kind=EvidenceKind.MODEL_OUTPUT,
        )
        role_input = DailyScreenerInput(
            run_id=context.run_id,
            execution_at=context.request.cycle_ts,
            evidence=(source,),
            trade_date=context.request.cycle_ts.date(),
            universe_as_of=context.request.cycle_ts.date(),
        )
        pick = DailyPick(
            trade_date=role_input.trade_date or context.request.cycle_ts.date(),
            ticker=context.request.ticker,
            universe_as_of=role_input.universe_as_of or context.request.cycle_ts.date(),
            bucket=Bucket.TREND_LEADER,
            rank=1,
            sector="Technology",
            score=0.82,
            evidence_ids=(source.evidence_id,),
        )
        return DailyScreenerOutput(run_id=context.run_id, picks=(pick,))

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Promote the ticker when its technical score clears the fixture gate."""
        score = require_value(
            context.technical_score, component=self.component, field_name="technical_score"
        )
        result = self.fixture(context) if score >= DAILY_PICK_THRESHOLD else None
        updated = replace(
            context,
            is_daily_pick=result is not None,
            daily_screener_output=result,
        )
        evidence = Evidence(
            evidence_id=f"{context.run_id}:03:screen",
            run_id=context.run_id,
            source="daily-screen-code",
            source_ref="policy://daily-screen/v1",
            observed_at=context.request.cycle_ts,
            captured_at=context.request.cycle_ts,
            confidence=1.0,
            kind=EvidenceKind.MODEL_OUTPUT,
            parent_evidence_ids=(context.evidence_trace[-1].evidence_id,),
        )
        return updated.add_stage(
            self.component, self.name, "오늘의 후보 50 범위에 포함", evidence=evidence
        )

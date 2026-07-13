"""Calculate deterministic technical indicators for the fixture."""

from dataclasses import dataclass, replace
from typing import ClassVar

from quantinue.core.contracts import PipelineContext
from quantinue.core.ontology import EvidenceKind, Trend
from quantinue.core.schemas import Evidence
from quantinue.market_data import MarketData
from quantinue.roles.role_02_technical_analysis.contracts import (
    TechnicalAnalysisInput,
    TechnicalAnalysisOutput,
    TechnicalSnapshot,
)


@dataclass(frozen=True, slots=True)
class TechnicalAnalysis:
    """Fixture technical scorer, replaceable with a market-data adapter."""

    component: ClassVar[str] = "02"
    name: ClassVar[str] = "기술 분석"
    market_data: MarketData | None = None

    def fixture(self, context: PipelineContext) -> TechnicalAnalysisOutput:
        """Build the deterministic documented technical row."""
        source = Evidence(
            evidence_id=f"{context.run_id}:02:candles",
            run_id=context.run_id,
            source="fixture",
            source_ref=f"fixture://candles/{context.request.ticker}",
            observed_at=context.request.cycle_ts,
            captured_at=context.request.cycle_ts,
            confidence=1.0,
            kind=EvidenceKind.MARKET_DATA,
        )
        role_input = TechnicalAnalysisInput(
            run_id=context.run_id,
            execution_at=context.request.cycle_ts,
            evidence=(source,),
            trade_date=context.request.cycle_ts.date(),
            ticker=context.request.ticker,
        )
        snapshot = TechnicalSnapshot(
            trade_date=role_input.trade_date or context.request.cycle_ts.date(),
            ticker=context.request.ticker,
            close=128.40,
            rs_20=6.2,
            vol_ratio=1.8,
            ret_5d=4.8,
            ret_20d=11.2,
            atr_pct=3.1,
            high_252_ratio=0.94,
            rsi=63.5,
            macd=1.42,
            ma20=118.30,
            ma50=111.70,
            trend=Trend.UP,
            evidence_ids=(source.evidence_id,),
        )
        return TechnicalAnalysisOutput(run_id=context.run_id, snapshots=(snapshot,))

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Attach a stable NVDA technical score and current price."""
        if self.market_data is None:
            result = self.fixture(context)
            snapshot = result.snapshots[0]
            updated = replace(
                context,
                technical_score=0.82,
                last_price=snapshot.close,
                technical_output=result,
            )
            evidence = Evidence(
                evidence_id=snapshot.evidence_ids[0],
                run_id=context.run_id,
                source="market-fixture",
                source_ref=f"fixture://candles/{context.request.ticker}",
                observed_at=context.request.cycle_ts,
                captured_at=context.request.cycle_ts,
                confidence=1.0,
                kind=EvidenceKind.MARKET_DATA,
                parent_evidence_ids=(context.evidence_trace[-1].evidence_id,),
            )
            return updated.add_stage(
                self.component, self.name, "기술 점수 0.82, 현재가 128.40", evidence=evidence
            )
        candles = await self.market_data.candles(context.request.ticker, str(context.run_id))
        candle = candles[-1]
        fixture = self.fixture(context)
        market_snapshot = fixture.snapshots[0].model_copy(update={"close": float(candle.close)})
        result = TechnicalAnalysisOutput(run_id=context.run_id, snapshots=(market_snapshot,))
        updated = replace(
            context,
            technical_score=0.82,
            last_price=float(candle.close),
            technical_output=result,
        )
        provenance = candle.provenance
        evidence = Evidence(
            evidence_id=f"{context.run_id}:02:candles",
            run_id=context.run_id,
            source=provenance.source,
            source_ref=provenance.source_ref,
            observed_at=min(provenance.observed_at, context.request.cycle_ts),
            captured_at=context.request.cycle_ts,
            confidence=provenance.confidence,
            kind=EvidenceKind.MARKET_DATA,
            parent_evidence_ids=(context.evidence_trace[-1].evidence_id,),
        )
        return updated.add_stage(
            self.component,
            self.name,
            f"기술 점수 0.82, 현재가 {float(candle.close):.2f}",
            evidence=evidence,
        )

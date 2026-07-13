"""Determine the broad market regime."""

from dataclasses import dataclass, replace
from typing import ClassVar

from quantinue.core.contracts import PipelineContext
from quantinue.core.ontology import EvidenceKind, Regime
from quantinue.core.schemas import Evidence
from quantinue.market_data import MarketData
from quantinue.roles.role_04_macro_analysis.contracts import (
    MacroAnalysisInput,
    MacroAnalysisOutput,
)


@dataclass(frozen=True, slots=True)
class MacroAnalysis:
    """Stable neutral-regime fixture for the first happy path."""

    component: ClassVar[str] = "04"
    name: ClassVar[str] = "매크로 분석"
    market_data: MarketData | None = None

    def fixture(self, context: PipelineContext) -> MacroAnalysisOutput:
        """Build the deterministic hourly macro snapshot."""
        source = Evidence(
            evidence_id=f"{context.run_id}:04:market",
            run_id=context.run_id,
            source="fixture",
            source_ref="fixture://macro/us",
            observed_at=context.request.cycle_ts,
            captured_at=context.request.cycle_ts,
            confidence=1.0,
            kind=EvidenceKind.MARKET_DATA,
        )
        role_input = MacroAnalysisInput(
            run_id=context.run_id,
            execution_at=context.request.cycle_ts,
            evidence=(source,),
            vix=18.2,
            nasdaq_ret=0.2,
            sp500_ret=0.1,
            rate=4.12,
            dollar=104.3,
        )
        return MacroAnalysisOutput(
            run_id=context.run_id,
            as_of=context.request.cycle_ts,
            regime=Regime.NEUTRAL,
            risk_score=0.42,
            vix=role_input.vix or 0.0,
            nasdaq_ret=role_input.nasdaq_ret or 0.0,
            sp500_ret=role_input.sp500_ret or 0.0,
            rate=role_input.rate or 0.0,
            dollar=role_input.dollar or 1.0,
            evidence_ids=(source.evidence_id,),
        )

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Attach a neutral regime and normalized risk score."""
        if self.market_data is None:
            result = self.fixture(context)
            updated = replace(
                context,
                macro_regime=result.regime,
                macro_risk_score=result.risk_score,
                macro_output=result,
            )
            evidence = Evidence(
                evidence_id=result.evidence_ids[0],
                run_id=context.run_id,
                source="market-fixture",
                source_ref="fixture://macro/us",
                observed_at=result.as_of,
                captured_at=context.request.cycle_ts,
                confidence=1.0,
                kind=EvidenceKind.MARKET_DATA,
            )
            return updated.add_stage(
                self.component, self.name, "중립 국면, 위험 점수 0.42", evidence=evidence
            )
        observations = await self.market_data.macro("DFF", str(context.run_id))
        observation = observations[-1]
        result = self.fixture(context)
        updated = replace(
            context,
            macro_regime=result.regime,
            macro_risk_score=result.risk_score,
            macro_output=result,
        )
        provenance = observation.provenance
        evidence = Evidence(
            evidence_id=result.evidence_ids[0],
            run_id=context.run_id,
            source=provenance.source,
            source_ref=provenance.source_ref,
            observed_at=min(provenance.observed_at, context.request.cycle_ts),
            captured_at=context.request.cycle_ts,
            confidence=provenance.confidence,
            kind=EvidenceKind.MARKET_DATA,
        )
        return updated.add_stage(
            self.component, self.name, "중립 국면, 위험 점수 0.42", evidence=evidence
        )

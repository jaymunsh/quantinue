"""Form 4 must not be read as if it were an 8-K.

`filings[0]` is simply the most recent filing, and large caps file insider
Form 4s constantly — so an ownership form routinely displaces the material
event we actually wanted to score. Worse, role 05 hardcoded `form_type="8-K"`,
so whatever arrived was labelled a material event downstream.

Without the ownership XML there is no way to tell an insider buy from a sale,
so the honest answer is silence, not a guessed score. Scoring it low would trip
`hard_negative_max` and block the buy; scoring it high would invent a signal.
"""

from datetime import UTC, datetime, timedelta

import pytest

from quantinue.core.contracts import PipelineContext, PipelineRequest
from quantinue.llm.provider import AnalysisResult, AnalysisTask, DeterministicAnalyzer
from quantinue.market_data.models import (
    Candle,
    MacroObservation,
    NewsItem,
    Provenance,
    SecSubmission,
    SecuritySnapshot,
)
from quantinue.roles.role_05_disclosure_analysis.service import DisclosureAnalysis

NOW = datetime(2026, 7, 14, 3, 0, tzinfo=UTC)
CIK = "0000320193"


def _filing(form: str, minutes_ago: int) -> SecSubmission:
    return SecSubmission(
        cik=CIK,
        company_name="Apple Inc.",
        accession_number=f"{CIK}-26-{minutes_ago:06d}",
        form=form,
        filed_at=NOW - timedelta(minutes=minutes_ago),
        primary_document=f"aapl-{form.lower().replace('/', '')}.htm",
        provenance=Provenance(
            source="sec-edgar",
            source_ref=f"https://data.sec.gov/submissions/CIK{CIK}.json",
            observed_at=NOW - timedelta(minutes=minutes_ago),
            captured_at=NOW,
            confidence=0.9,
            execution_id="run-form4",
        ),
    )


class _SecMarketData:
    def __init__(self, filings: tuple[SecSubmission, ...]) -> None:
        self._filings = filings

    async def screener(self, execution_id: str) -> tuple[SecuritySnapshot, ...]:
        del execution_id
        return ()

    async def candles(self, ticker: str, execution_id: str) -> tuple[Candle, ...]:
        del ticker, execution_id
        return ()

    async def macro(self, series: str, execution_id: str) -> tuple[MacroObservation, ...]:
        del series, execution_id
        return ()

    async def rss(self, execution_id: str) -> tuple[NewsItem, ...]:
        del execution_id
        return ()

    async def sec_cik_for_ticker(self, ticker: str, execution_id: str) -> str | None:
        del ticker, execution_id
        return CIK

    async def sec_submissions(self, cik: str, execution_id: str) -> tuple[SecSubmission, ...]:
        del cik, execution_id
        return self._filings


class _CountingAnalyzer:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def analyze(self, task: AnalysisTask, prompt: str) -> AnalysisResult:
        self.prompts.append(prompt)
        return await DeterministicAnalyzer().analyze(task, prompt)


def _context() -> PipelineContext:
    return PipelineContext(request=PipelineRequest(ticker="AAPL", cycle_ts=NOW))


async def _run(filings: tuple[SecSubmission, ...]) -> tuple[PipelineContext, _CountingAnalyzer]:
    analyzer = _CountingAnalyzer()
    service = DisclosureAnalysis(analyzer=analyzer, market_data=_SecMarketData(filings))
    return await service.execute(_context()), analyzer


@pytest.mark.anyio
async def test_a_recent_form4_does_not_displace_the_material_filing() -> None:
    # Given: an insider form filed after the 8-K we actually care about
    updated, analyzer = await _run((_filing("4", 1), _filing("8-K", 60)))

    # Then: the 8-K is what gets scored
    assert updated.disclosure_source is not None
    assert updated.disclosure_source.form_type == "8-K"
    assert len(analyzer.prompts) == 1


@pytest.mark.anyio
async def test_form4_only_feed_abstains_without_calling_the_model() -> None:
    updated, analyzer = await _run((_filing("4", 1), _filing("4/A", 30)))

    assert analyzer.prompts == []
    assert updated.disclosure_score is None


@pytest.mark.anyio
async def test_form_type_is_recorded_as_filed_not_assumed() -> None:
    # The old code labelled everything "8-K"; the record must reflect reality.
    updated, _ = await _run((_filing("10-Q", 5),))

    assert updated.disclosure_source is not None
    assert updated.disclosure_source.form_type == "10-Q"


@pytest.mark.anyio
async def test_form4_is_never_scored_as_a_hard_negative() -> None:
    # A score of 0.0 would trip hard_negative_max and block every buy for a
    # company whose only recent filing is routine insider paperwork.
    updated, _ = await _run((_filing("4", 1),))

    assert updated.disclosure_score is None

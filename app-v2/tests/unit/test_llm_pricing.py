from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantinue.llm.budget import BudgetedAnalyzer, ModelPrice
from quantinue.llm.provider import AnalysisTask
from quantinue.llm.usage_limits import TokenUsage
from quantinue.orchestration.policy import load_mvp2_config

from .test_llm_budget import RecordingLedger, StubAnalyzer


@pytest.mark.parametrize(
    ("field", "invalid_rate"),
    [
        ("input_usd_per_1m", None),
        ("input_usd_per_1m", 0),
        ("input_usd_per_1m", -1),
        ("input_usd_per_1m", "NaN"),
        ("output_usd_per_1m", None),
        ("output_usd_per_1m", 0),
        ("output_usd_per_1m", -1),
        ("output_usd_per_1m", "NaN"),
    ],
)
def test_billable_model_rate_must_be_present_positive_and_finite(
    field: str,
    invalid_rate: str | int | None,
) -> None:
    price: dict[str, str | int | None] = {
        "input_usd_per_1m": "0.75",
        "output_usd_per_1m": "4.50",
    }
    price[field] = invalid_rate

    with pytest.raises(ValidationError):
        _ = ModelPrice.model_validate(price)


@pytest.mark.anyio
async def test_standard_gpt_5_4_mini_usage_records_exact_known_daily_cost() -> None:
    config = load_mvp2_config(Path(__file__).parents[2] / "config" / "pipeline.yaml")
    price = config.budget.model_pricing["gpt-5.4-mini"]
    ledger = RecordingLedger()
    rows = (
        (AnalysisTask.STRATEGY, 45_270, 5_054),
        (AnalysisTask.CRITIC, 25_221, 3_691),
    )

    for task, input_tokens, output_tokens in rows:
        analyzer = BudgetedAnalyzer(
            StubAnalyzer(
                TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                ),
                model="gpt-5.4-mini",
            ),
            ledger=ledger,
            daily_limit_usd=3,
            pricing={"gpt-5.4-mini": price},
            now=lambda: datetime(2026, 7, 22, 4, 0, tzinfo=UTC),
        )
        _ = await analyzer.analyze(task, "known usage")

    assert [record.est_cost_usd for record in ledger.records] == [
        Decimal("0.0566955"),
        Decimal("0.03552525"),
    ]
    assert sum(
        (record.est_cost_usd for record in ledger.records), Decimal(0)
    ) == Decimal("0.09222075")

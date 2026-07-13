"""Bounded redacted detail retained with each terminal pipeline run."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DisplayTitle = Annotated[str, StringConstraints(max_length=200)]
DisplayText = Annotated[str, StringConstraints(max_length=1_000)]
DisplaySource = Annotated[str, StringConstraints(max_length=120)]
DisplayReference = Annotated[str, StringConstraints(max_length=512, strip_whitespace=False)]
DisplayDecision = Annotated[str, StringConstraints(max_length=64)]
DisplayBlocker = Annotated[str, StringConstraints(max_length=240)]


class RedactedDetailModel(BaseModel):
    """Strict immutable base for administrator-safe terminal detail."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid", str_strip_whitespace=True)


class CollectionFact(RedactedDetailModel):
    """One bounded collection fact suitable for administrator display."""

    title: DisplayTitle = ""
    summary: DisplayText = ""
    source: DisplaySource = ""
    reference: DisplayReference = ""
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class StrategyDetail(RedactedDetailModel):
    """Bounded strategist result without model inputs or provider payloads."""

    proposal: DisplayDecision = ""
    rationale: DisplayText = ""
    gate: DisplayDecision = ""
    blockers: tuple[DisplayBlocker, ...] = Field(default=(), max_length=12)
    conviction: float | None = Field(default=None, ge=0.0, le=1.0)


class CriticDetail(RedactedDetailModel):
    """Bounded critic verdict without exception or provider detail."""

    verdict: DisplayDecision = ""
    rationale: DisplayText = ""
    layer: DisplayDecision = ""


class TerminalRunDetail(RedactedDetailModel):
    """Safe collection-to-critic detail with legacy-safe empty placeholders."""

    disclosure: CollectionFact = Field(default_factory=CollectionFact)
    news: CollectionFact = Field(default_factory=CollectionFact)
    strategy: StrategyDetail = Field(default_factory=StrategyDetail)
    critic: CriticDetail = Field(default_factory=CriticDetail)

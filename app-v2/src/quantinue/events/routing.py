"""Typed, deterministic routing for untrusted intraday event documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from quantinue.core.news_trust import NEWS_TRUST_POLICY, registrable_domain

_TICKER_PATTERN: Final = re.compile(r"^[A-Z0-9.-]{1,12}$")
_DIRECT_EVENT_TYPES: Final[dict[str, str]] = {
    "earnings": "earnings",
    "guidance": "guidance",
    "merger": "merger_acquisition",
    "acquisition": "merger_acquisition",
    "regulatory": "regulatory",
    "offering": "offering",
    "insider_trade": "insider_trade",
}
_HEADLINE_EVENT_TYPES: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("guidance", ("guidance", "outlook", "forecast")),
    ("earnings", ("earnings", "quarterly results", "revenue", "profit")),
    ("merger_acquisition", ("merger", "acquisition", "acquire", "takeover")),
    ("regulatory", ("sec investigation", "doj", "fda", "regulator", "lawsuit")),
    ("offering", ("public offering", "share offering", "stock offering", "dilution")),
    ("insider_trade", ("insider purchase", "insider sale", "form 4")),
)
_SEC_FORM_EVENT_TYPES: Final[dict[str, str]] = {
    "10-K": "earnings",
    "10-Q": "earnings",
    "8-K": "regulatory",
    "S-1": "offering",
    "S-3": "offering",
    "4": "insider_trade",
}


class RejectionCode(StrEnum):
    """Stable machine-readable reasons emitted before any model call."""

    UNSUPPORTED_SOURCE = "unsupported_source"
    BLOCKED_SOURCE = "blocked_source"
    MALFORMED_TICKER = "malformed_ticker"
    MALFORMED_DOCUMENT = "malformed_document"
    UNRELATED_TICKER = "unrelated_ticker"
    UNSUPPORTED_CLAIM = "unsupported_claim"


class EventCandidate(BaseModel):
    """One immutable raw-version lineage parsed from a database row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: int
    raw_version_id: int
    content_hash: str
    source_name: str
    source_url: str
    source_sequence: str
    event_type: str
    occurred_at: AwareDatetime
    ticker: str
    raw_text: str


@dataclass(frozen=True, slots=True)
class AcceptedRoute:
    """A material event linked to exactly one canonical scope ticker."""

    event_id: int
    raw_version_id: int
    content_hash: str
    source_name: str
    source_sequence: str
    ticker: str
    event_type: str


@dataclass(frozen=True, slots=True)
class RejectedRoute:
    """A document rejected without retaining its body in the decision."""

    event_id: int
    raw_version_id: int
    content_hash: str
    source_name: str
    source_sequence: str
    reason: RejectionCode


RoutingDecision = AcceptedRoute | RejectedRoute


class _SecBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    form_type: str


class _NewsBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    headline: str
    source: str


@dataclass(frozen=True, slots=True)
class MalformedEventBodyError(Exception):
    """An external body did not parse into the source-specific type."""

    source_name: str


def _rejected(candidate: EventCandidate, reason: RejectionCode) -> RejectedRoute:
    return RejectedRoute(
        event_id=candidate.event_id,
        raw_version_id=candidate.raw_version_id,
        content_hash=candidate.content_hash,
        source_name=candidate.source_name,
        source_sequence=candidate.source_sequence,
        reason=reason,
    )


def _headline_event_type(headline: str) -> str | None:
    normalized = headline.casefold()
    for event_type, markers in _HEADLINE_EVENT_TYPES:
        if any(marker in normalized for marker in markers):
            return event_type
    return None


def _material_event_type(candidate: EventCandidate) -> str | None:
    direct = _DIRECT_EVENT_TYPES.get(candidate.event_type.casefold())
    if direct is not None:
        return direct
    try:
        if candidate.source_name == "sec":
            body = _SecBody.model_validate_json(candidate.raw_text)
            return _SEC_FORM_EVENT_TYPES.get(body.form_type.upper())
        if candidate.source_name in {"news", "wire"}:
            body = _NewsBody.model_validate_json(candidate.raw_text)
            return _headline_event_type(body.headline)
    except ValidationError as error:
        raise MalformedEventBodyError(candidate.source_name) from error
    return None


def _initial_rejection(
    candidate: EventCandidate,
    in_scope_tickers: frozenset[str],
) -> RejectionCode | None:
    if candidate.source_name not in {"sec", "news", "wire"}:
        return RejectionCode.UNSUPPORTED_SOURCE
    if not _TICKER_PATTERN.fullmatch(candidate.ticker):
        return RejectionCode.MALFORMED_TICKER
    if candidate.ticker not in in_scope_tickers:
        return RejectionCode.UNRELATED_TICKER
    if candidate.source_name == "sec":
        return (
            None
            if registrable_domain(candidate.source_url) == "sec.gov"
            else RejectionCode.BLOCKED_SOURCE
        )
    return (
        RejectionCode.BLOCKED_SOURCE
        if NEWS_TRUST_POLICY.is_blocked(candidate.source_url)
        else None
    )


def route_candidate(
    candidate: EventCandidate,
    in_scope_tickers: frozenset[str],
) -> RoutingDecision:
    """Route a typed document using only deterministic, pre-LLM checks."""
    rejection = _initial_rejection(candidate, in_scope_tickers)
    if rejection is not None:
        return _rejected(candidate, rejection)
    try:
        event_type = _material_event_type(candidate)
    except MalformedEventBodyError:
        return _rejected(candidate, RejectionCode.MALFORMED_DOCUMENT)
    if event_type is None:
        return _rejected(candidate, RejectionCode.UNSUPPORTED_CLAIM)
    return AcceptedRoute(
        event_id=candidate.event_id,
        raw_version_id=candidate.raw_version_id,
        content_hash=candidate.content_hash,
        source_name=candidate.source_name,
        source_sequence=candidate.source_sequence,
        ticker=candidate.ticker,
        event_type=event_type,
    )

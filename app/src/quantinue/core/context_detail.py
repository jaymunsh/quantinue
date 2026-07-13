"""Project role facts into bounded terminal detail."""

from __future__ import annotations

from typing import Protocol

from quantinue.core.terminal_detail import (
    CollectionFact,
    CriticDetail,
    StrategyDetail,
    TerminalRunDetail,
)


class _DisclosureDetailSource(Protocol):
    @property
    def title(self) -> str: ...

    @property
    def summary(self) -> str: ...

    @property
    def source(self) -> str: ...

    @property
    def source_ref(self) -> str: ...


class _NewsDetailSource(Protocol):
    @property
    def title(self) -> str: ...

    @property
    def summary(self) -> str: ...

    @property
    def source(self) -> str: ...

    @property
    def url(self) -> str: ...


class _StrategyDetailOutput(Protocol):
    @property
    def side(self) -> str: ...

    @property
    def summary(self) -> str: ...

    @property
    def gate_passed(self) -> bool: ...

    @property
    def blockers(self) -> tuple[str, ...]: ...

    @property
    def conviction(self) -> float: ...


class _CriticDetailOutput(Protocol):
    @property
    def decision(self) -> str: ...

    @property
    def objection(self) -> str | None: ...

    @property
    def decided_layer(self) -> str: ...


class _DetailContext(Protocol):
    @property
    def disclosure_source(self) -> _DisclosureDetailSource | None: ...

    @property
    def news_source(self) -> _NewsDetailSource | None: ...

    @property
    def disclosure_score(self) -> float | None: ...

    @property
    def news_score(self) -> float | None: ...

    @property
    def strategy_output(self) -> _StrategyDetailOutput | None: ...

    @property
    def critic_verdict(self) -> _CriticDetailOutput | None: ...


def terminal_detail_from_context(context: _DetailContext) -> TerminalRunDetail:
    """Build display-safe detail without parsing localized stage summaries."""
    disclosure = context.disclosure_source
    news = context.news_source
    strategy = context.strategy_output
    critic = context.critic_verdict
    return TerminalRunDetail(
        disclosure=CollectionFact(
            title=disclosure.title[:200] if disclosure is not None else "",
            summary=disclosure.summary[:1_000] if disclosure is not None else "",
            source=disclosure.source[:120] if disclosure is not None else "",
            reference=disclosure.source_ref[:512] if disclosure is not None else "",
            score=context.disclosure_score,
        ),
        news=CollectionFact(
            title=news.title[:200] if news is not None else "",
            summary=news.summary[:1_000] if news is not None else "",
            source=news.source[:120] if news is not None else "",
            reference=news.url[:512] if news is not None else "",
            score=context.news_score,
        ),
        strategy=StrategyDetail(
            proposal=strategy.side if strategy is not None else "",
            rationale=strategy.summary[:1_000] if strategy is not None else "",
            gate=("passed" if strategy.gate_passed else "blocked") if strategy is not None else "",
            blockers=tuple(blocker[:240] for blocker in strategy.blockers)
            if strategy is not None
            else (),
            conviction=strategy.conviction if strategy is not None else None,
        ),
        critic=CriticDetail(
            verdict=critic.decision if critic is not None else "",
            rationale=(critic.objection or "")[:1_000] if critic is not None else "",
            layer=critic.decided_layer if critic is not None else "",
        ),
    )

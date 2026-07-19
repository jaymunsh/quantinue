"""Critic cache-state source is renamed so lineage `source` stays uniform."""

from decimal import Decimal

from quantinue.db.domain_records import CriticVerdictWrite


def test_critic_verdict_write_uses_verdict_source() -> None:
    write = CriticVerdictWrite(
        signal_id=1,
        ticker="NVDA",
        decision="pass",
        category="pipeline_gate",
        objection="accepted",
        confidence=Decimal("0.8"),
        decided_layer="gate",
    )

    assert write.verdict_source == "fresh"
    # lineage `source`(sec/rss 등 출처)와 이름이 겹치지 않아야 재현 계약이 성립.
    assert not hasattr(write, "source")

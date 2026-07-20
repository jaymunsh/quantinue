"""Immutable input and output contracts for role 01."""

from datetime import date, timedelta
from typing import Literal

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from quantinue.core.schemas import AwareDateTime, ContractModel, Evidence


class EvidenceBoundInput(ContractModel):
    """Common evidence-lineage boundary used by deterministic roles."""

    run_id: str = Field(min_length=1)
    execution_at: AwareDateTime
    evidence: tuple[Evidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_coherent_evidence(self) -> "EvidenceBoundInput":
        """Reject unavailable, stale, cross-run, or contradictory evidence."""
        by_id: dict[str, Evidence] = {}
        for item in self.evidence:
            if item.run_id != self.run_id:
                code = "evidence_run_mismatch"
                message = "evidence run_id does not match execution run"
                raise PydanticCustomError(code, message)
            if item.captured_at > self.execution_at:
                code = "future_evidence"
                message = "future evidence is unavailable at execution time"
                raise PydanticCustomError(code, message)
            if self.execution_at - item.captured_at > timedelta(minutes=5):
                code = "stale_evidence"
                message = "stale evidence exceeds five-minute limit"
                raise PydanticCustomError(code, message)
            prior = by_id.get(item.evidence_id)
            if prior is not None and prior != item:
                code = "contradictory_evidence"
                message = "contradictory evidence uses the same evidence_id"
                raise PydanticCustomError(code, message)
            by_id[item.evidence_id] = item
        available = frozenset(by_id)
        missing_parent = any(
            parent not in available for item in self.evidence for parent in item.parent_evidence_ids
        )
        if missing_parent:
            code = "missing_evidence_parent"
            message = "evidence lineage references an unavailable parent"
            raise PydanticCustomError(code, message)
        return self


class ListedSecurity(ContractModel):
    """One raw US-listed instrument from the free screener feed."""

    ticker: str = Field(min_length=1, max_length=12)
    company_name: str = Field(min_length=1)
    market_cap: int = Field(gt=0)
    security_type: str = Field(min_length=1)


class UniverseScreenerInput(EvidenceBoundInput):
    """Role 01 boundary for a weekly listing snapshot."""

    as_of_date: date | None = None
    listings: tuple[ListedSecurity, ...] = ()


class UniverseMember(ContractModel):
    """Persistable role 01 universe row."""

    as_of_date: date
    ticker: str = Field(min_length=1, max_length=12)
    company_name: str = Field(min_length=1)
    # ge=0인 이유: 상장폐지된 보유를 이월할 때 마지막 관측 시총이 없으면 0이
    # 된다. 시총 0인 상장 종목은 데이터 오류지만, 시총 0인 이월분은 "더 이상
    # 시장이 값을 매기지 않는다"는 사실 그대로다.
    market_cap: int = Field(ge=0)
    # 이 행이 어디서 왔는지 — 상장 피드인가, 우리가 들고 있어서 이월했는가.
    # 라벨 없이 union만 하면 "왜 상장 피드에 없는 종목이 유니버스에 있나"에
    # 답할 수 없고, 그 자체가 다음 세대의 유령이 된다.
    listing_status: Literal["listed", "held_delisted"] = "listed"
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class UniverseScreenerOutput(ContractModel):
    """Top common-stock universe with its execution identity."""

    run_id: str = Field(min_length=1)
    generated_at: AwareDateTime
    # 상한이 universe_size(2000)와 같으면 상장폐지 보유 이월분이 계약 위반으로
    # 튄다 — 이월분은 캡 **밖에서** 더해지기 때문이다. 여유를 준다.
    members: tuple[UniverseMember, ...] = Field(max_length=2500)

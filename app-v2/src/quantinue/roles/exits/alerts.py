"""Human-readable defence-line alerts shared by daily and intraday exits."""

from datetime import date
from typing import Final

from quantinue.roles.exits.contracts import ExitDecision

EXIT_REASON_LABELS: Final[dict[str, str]] = {
    "stop": "손절",
    "take_profit": "익절",
    "time": "시간 청산",
    "thesis_break": "논지 붕괴(하드)",
    "thesis_soft": "매도 판단",
}


def format_exit_alert(as_of: date, decisions: tuple[ExitDecision, ...]) -> str:
    """Format one alert only after closes have durably completed.

    가격은 **두 자리로 고정한다.** Decimal을 그대로 넣으면 자릿수가 값마다
    달라져 한 알림 안에 ``$139.5``와 ``$80``이 섞인다. 매일 받는 알림에서
    그 흔들림은 "이 시스템은 돈을 대충 센다"로 읽힌다.
    """
    lines = [f"🛡 {as_of} 방어선 발동 {len(decisions)}건"]
    lines.extend(
        f"- {decision.position.ticker} {decision.position.quantity}주 · "
        f"{EXIT_REASON_LABELS.get(decision.reason.value, decision.reason.value)}"
        f" @ ${decision.reference_price:,.2f}"
        for decision in decisions
    )
    return "\n".join(lines)

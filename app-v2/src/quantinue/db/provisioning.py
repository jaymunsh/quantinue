"""Canonical account roster provisioned into the local ledger.

These are internal simulated accounts — rows in `tb_account`, not broker
accounts. Only the single Wave-0 paper account ever reaches Alpaca.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from quantinue.db.domain_records import AccountWrite

TEST_ACCOUNT_PREFIX: Final = "TEST-"


@dataclass(frozen=True, slots=True)
class AccountSpec:
    """One provisioned account: who it is and how much it starts with."""

    broker_account_id: str
    inv_type: Literal["aggressive", "conservative"]
    equity: Decimal

    @property
    def is_test(self) -> bool:
        """Return whether this is a test account rather than a demo one."""
        return self.broker_account_id.startswith(TEST_ACCOUNT_PREFIX)


# 2026-07-19 확정(문성혁): 테스트 2 + 데모 5. 기존 $1M·$50K 안은 폐기.
DEMO_ACCOUNTS: Final[tuple[AccountSpec, ...]] = (
    AccountSpec("TEST-AGGRESSIVE-01", "aggressive", Decimal("100000.00")),
    AccountSpec("TEST-CONSERVATIVE-01", "conservative", Decimal("100000.00")),
    AccountSpec("DEMO-AGGRESSIVE-01", "aggressive", Decimal("150000.00")),
    AccountSpec("DEMO-AGGRESSIVE-02", "aggressive", Decimal("100000.00")),
    AccountSpec("DEMO-AGGRESSIVE-03", "aggressive", Decimal("5000.00")),
    AccountSpec("DEMO-CONSERVATIVE-01", "conservative", Decimal("100000.00")),
    AccountSpec("DEMO-CONSERVATIVE-02", "conservative", Decimal("5000.00")),
)


def account_writes() -> tuple[AccountWrite, ...]:
    """Project the roster into write records; a new account holds only cash."""
    return tuple(
        AccountWrite(
            broker_account_id=spec.broker_account_id,
            cash=spec.equity,
            equity=spec.equity,
            buying_power=spec.equity,
            inv_type=spec.inv_type,
        )
        for spec in DEMO_ACCOUNTS
    )

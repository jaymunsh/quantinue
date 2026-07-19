#!/usr/bin/env python
"""Provision the canonical local account roster.

These are internal simulated accounts (rows in `tb_account`), not broker
accounts — running this costs nothing and touches no external service.

Safe to re-run: existing accounts keep their balances, so a live ledger is
never reset by a second invocation.

    uv run python scripts/provision_accounts.py
"""

# ruff: noqa: T201 - 운영 스크립트는 stdout이 출력 채널이다

import asyncio
import os
import sys

from quantinue.db.domain import PostgresDomainRepository
from quantinue.db.postgres import PostgresRunStore
from quantinue.db.provisioning import DEMO_ACCOUNTS, account_writes


async def main() -> int:
    """Create any missing accounts and report the resulting roster."""
    database_url = os.environ.get("QUANTINUE_DATABASE_URL")
    if not database_url:
        print("QUANTINUE_DATABASE_URL is not set", file=sys.stderr)
        return 1
    store = PostgresRunStore(database_url)
    await store.initialize()
    domain = PostgresDomainRepository(database_url)
    await domain.initialize()
    for spec, write in zip(DEMO_ACCOUNTS, account_writes(), strict=True):
        account_id = await domain.save_account(write)
        label = "test" if spec.is_test else "demo"
        print(
            f"  [{label:4}] {spec.broker_account_id:24} "
            f"{spec.inv_type:12} ${spec.equity:>12,.2f}  -> id={account_id}"
        )
    print(f"\n{len(DEMO_ACCOUNTS)} accounts provisioned (existing balances untouched).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

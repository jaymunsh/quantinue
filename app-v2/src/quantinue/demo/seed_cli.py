#!/usr/bin/env python
"""Seed the demo ledger from the scenario contract.

    QUANTINUE_DATABASE_URL=... uv run python -m quantinue.demo.seed_cli

로그인 비밀번호는 환경에서 읽고, 없으면 생성해 터미널에 한 번만 보여준다
(provision_accounts.py와 같은 규칙):

    QUANTINUE_DEMO_ADMIN_PASSWORD   관제실 로그인
    QUANTINUE_DEMO_USER_PASSWORD    /me 사용자 로그인
"""

# ruff: noqa: T201 - 촬영 준비 스크립트는 stdout이 출력 채널이다

import asyncio
import os
import secrets
import sys
from dataclasses import replace

from quantinue.api.passwords import hash_password
from quantinue.demo.app import _DEMO_DB_MARKER
from quantinue.demo.scenario import build_scenario
from quantinue.demo.seed import DemoUser, seed_demo_ledger

_GENERATED_PASSWORD_BYTES = 12


def _password(variable: str, label: str) -> str:
    """Read a password from the environment, or mint one and show it once."""
    supplied = os.environ.get(variable, "").strip()
    if supplied:
        return supplied
    generated = secrets.token_urlsafe(_GENERATED_PASSWORD_BYTES)
    print(f"  ⚠️  {label} 비밀번호를 생성했습니다 (다시 표시되지 않습니다): {generated}")
    return generated


async def main() -> int:
    """Seed the S1 opening ledger into the disposable demo database."""
    database_url = os.environ.get("QUANTINUE_DATABASE_URL", "")
    if _DEMO_DB_MARKER not in database_url:
        print("데모 seed는 5490 일회용 DB에만 쓴다 — URL을 확인하라", file=sys.stderr)
        return 1
    scenario = build_scenario()
    spec = replace(
        scenario.seed,
        users=(
            DemoUser(
                login_id="admin",
                display_name="관리자",
                role="admin",
                password_hash=hash_password(
                    _password("QUANTINUE_DEMO_ADMIN_PASSWORD", "admin")
                ),
            ),
            DemoUser(
                login_id="demo",
                display_name="데모 사용자",
                role="user",
                password_hash=hash_password(
                    _password("QUANTINUE_DEMO_USER_PASSWORD", "demo")
                ),
                owns_account=True,
            ),
        ),
    )
    report = await seed_demo_ledger(database_url, spec)
    print(
        f"seeded: account={report.account_id} positions={report.seeded_positions} "
        f"signals={report.signal_ids} trade_date={scenario.trade_date}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

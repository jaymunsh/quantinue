#!/usr/bin/env python
"""Provision the canonical local account roster and the logins that own it.

These are internal simulated accounts (rows in `tb_account`), not broker
accounts — running this costs nothing and touches no external service.

Safe to re-run: existing accounts keep their balances and existing logins keep
their passwords, so a live ledger is never reset by a second invocation.

    uv run python scripts/provision_accounts.py

Passwords come from the environment and are never written to source or logs:

    QUANTINUE_SEED_ADMIN_PASSWORD   관리자 비밀번호 (없으면 생성해 한 번 출력)
    QUANTINUE_SEED_USER_PASSWORD    데모 유저 공용 비밀번호 (같은 규칙)
    QUANTINUE_SEED_RESET_PASSWORDS  1이면 기존 비밀번호를 덮어쓴다

⚠️ 이 스크립트를 처음 돌리는 순간 `tb_user`에 행이 생기고, 그때부터 관제실이
부트스트랩 예외(W-D2)를 잃고 로그인을 요구한다.
"""

# ruff: noqa: T201 - 운영 스크립트는 stdout이 출력 채널이다

import asyncio
import os
import secrets
import sys

from quantinue.api.passwords import hash_password
from quantinue.db.domain import PostgresDomainRepository
from quantinue.db.postgres import PostgresRunStore
from quantinue.db.provisioning import DEMO_ACCOUNTS, DEMO_USERS, account_writes
from quantinue.db.users import UserWrite

_GENERATED_PASSWORD_BYTES = 12


def _password(variable: str, label: str) -> str:
    """Read a password from the environment, or mint one and show it once."""
    supplied = os.environ.get(variable, "").strip()
    if supplied:
        return supplied
    # 생성한 비밀번호는 여기서 한 번만 보인다. 구조화 로그가 아니라 운영자
    # 터미널이고, 안 보여주면 방금 만든 계정으로 아무도 들어갈 수 없다.
    generated = secrets.token_urlsafe(_GENERATED_PASSWORD_BYTES)
    print(f"  ⚠️  {label} 비밀번호를 생성했습니다 (다시 표시되지 않습니다): {generated}")
    return generated


async def main() -> int:
    """Create any missing accounts and logins, then report the resulting roster."""
    database_url = os.environ.get("QUANTINUE_DATABASE_URL")
    if not database_url:
        print("QUANTINUE_DATABASE_URL is not set", file=sys.stderr)
        return 1
    reset_passwords = os.environ.get("QUANTINUE_SEED_RESET_PASSWORDS", "") == "1"

    store = PostgresRunStore(database_url)
    await store.initialize()
    domain = PostgresDomainRepository(database_url)
    await domain.initialize()

    print("계좌")
    for spec, write in zip(DEMO_ACCOUNTS, account_writes(), strict=True):
        account_id = await domain.save_account(write)
        label = "test" if spec.is_test else "demo"
        print(
            f"  [{label:4}] {spec.broker_account_id:24} "
            f"{spec.inv_type:12} ${spec.equity:>12,.2f}  -> id={account_id}"
        )

    print("\n계정")
    admin_password = _password("QUANTINUE_SEED_ADMIN_PASSWORD", "관리자")
    user_password = _password("QUANTINUE_SEED_USER_PASSWORD", "데모 유저 공용")
    unowned: list[str] = []
    for spec in DEMO_USERS:
        plaintext = admin_password if spec.role == "admin" else user_password
        user_id = await domain.save_user(
            UserWrite(
                login_id=spec.login_id,
                display_name=spec.display_name,
                role=spec.role,
                password_hash=hash_password(plaintext),
            ),
            reset_password=reset_passwords,
        )
        owned = "—"
        if spec.broker_account_id is not None:
            attached = await domain.set_account_owner(spec.broker_account_id, user_id)
            owned = spec.broker_account_id if attached else f"{spec.broker_account_id} (없음!)"
            if not attached:
                unowned.append(spec.broker_account_id)
        print(f"  [{spec.role:5}] {spec.login_id:8} {spec.display_name:14} -> {owned}")

    note = "passwords reset" if reset_passwords else "existing passwords kept"
    print(
        f"\n{len(DEMO_ACCOUNTS)} accounts and {len(DEMO_USERS)} logins provisioned "
        f"(balances untouched, {note})."
    )
    if unowned:
        # 조용히 넘어가면 그 유저는 로그인해서 404만 본다.
        print(f"⚠️  소유자를 붙이지 못한 계좌: {', '.join(unowned)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

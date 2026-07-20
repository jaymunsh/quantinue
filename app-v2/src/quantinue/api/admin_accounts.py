"""Account CRUD — the administrator's only write path (W3-3).

이 앱에서 사람이 상태를 바꿀 수 있는 유일한 자리다. 나머지 화면은 전부 읽기
전용이고 유저 role의 쓰기 엔드포인트는 **0으로 유지된다**
(``tests/unit/test_route_audit.py``가 동적으로 강제한다).

여기 있는 것은 전부 ``/admin`` 아래 산다. 가드가 "유저 구역과 갈림길을 뺀
나머지는 관리자"로 기본 거부하므로, 이 라우터는 자기 권한을 따로 검사하지
않는다 — 검사가 두 곳에 있으면 한 곳만 고쳐지는 날이 온다.

폼 위조(CSRF)는 세션 쿠키의 ``same_site="lax"``가 막는다. lax는 교차 사이트
POST에 쿠키를 실어 보내지 않으므로, 남의 페이지에서 이 폼을 제출해도 세션이
없는 요청이 된다. ⚠️ 쿠키 정책을 ``none``으로 바꾸면 이 방어가 사라진다.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003 - FastAPI가 런타임에 폼 타입을 해석한다
from decimal import Decimal  # noqa: TC003 - FastAPI가 런타임에 폼 타입을 해석한다
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)

from quantinue.api.account_roster import account_roster_view
from quantinue.api.auth import session_user
from quantinue.api.passwords import hash_password
from quantinue.db.domain_records import AccountWrite
from quantinue.db.users import UserWrite

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

# 원장이 허용하는 값과 같아야 한다. 화면이 더 넓은 집합을 받으면 DB 제약이
# 500으로 거절하고, 그건 사용자에게 "서버가 고장났다"로 보인다.
PROFILES: Final = ("aggressive", "conservative")
STATUSES: Final = ("active", "paused", "closed")


def build_admin_accounts_router(reads: object | None, templates: Jinja2Templates) -> APIRouter:
    """Build the account roster page and the three writes it offers."""
    router = APIRouter()

    def _require(name: str) -> object:
        writer = getattr(reads, name, None)
        if writer is None:
            # 메모리 스토어에는 계좌 원장이 없다. 쓰기를 흉내 내 성공을
            # 돌려주면 화면이 "바꿨다"고 말하고 아무것도 안 바뀐다.
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return writer

    @router.get("/admin/accounts")
    async def accounts_page(request: Request) -> HTMLResponse:
        reader = getattr(reads, "account_overviews", None)
        roster = account_roster_view(() if reader is None else await reader())
        return templates.TemplateResponse(
            request=request,
            name="admin_accounts.html",
            context={
                "roster": roster,
                "profiles": PROFILES,
                "statuses": STATUSES,
                "current_user": session_user(request),
            },
        )

    @router.post("/admin/accounts")
    async def open_account(  # noqa: PLR0913 - 계좌 개설 폼의 필드가 곧 인자다
        broker_account_id: Annotated[str, Form()],
        inv_type: Annotated[str, Form()],
        opening_cash: Annotated[Decimal, Form()],
        login_id: Annotated[str, Form()],
        display_name: Annotated[str, Form()],
        password: Annotated[str, Form()],
    ) -> RedirectResponse:
        """Open one account and the single login that owns it (1유저=1계좌)."""
        _reject_unknown(inv_type, PROFILES)
        if opening_cash < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY)
        save_account = _require("save_account")
        save_user = _require("save_user")
        set_owner = _require("set_account_owner")
        # 계좌가 먼저다. 유저를 먼저 만들면 계좌 생성이 실패했을 때 로그인은
        # 되는데 볼 계좌가 없는 사람이 남는다 — /me가 404만 보이는 상태다.
        _ = await save_account(  # type: ignore[operator]
            AccountWrite(broker_account_id, opening_cash, opening_cash, opening_cash)
        )
        _ = await _require("set_account_profile")(broker_account_id, inv_type)  # type: ignore[operator]
        user_id = await save_user(  # type: ignore[operator]
            UserWrite(
                login_id=login_id,
                display_name=display_name,
                role="user",
                password_hash=hash_password(password),
            ),
            reset_password=False,
        )
        _ = await set_owner(broker_account_id, int(user_id))  # type: ignore[operator]
        return _back()

    @router.post("/admin/accounts/{broker_account_id}/profile")
    async def change_profile(
        broker_account_id: str, inv_type: Annotated[str, Form()]
    ) -> RedirectResponse:
        _reject_unknown(inv_type, PROFILES)
        changed = await _require("set_account_profile")(broker_account_id, inv_type)  # type: ignore[operator]
        return _back_or_missing(changed)

    @router.post("/admin/jobs/release")
    async def release_slot(
        job_name: Annotated[str, Form()], slot_date: Annotated[date, Form()]
    ) -> RedirectResponse:
        """Unlock a slot stuck in ``running`` — the runner reruns it, not us."""
        released = await _require("release_job_slot")(job_name, slot_date)  # type: ignore[operator]
        if not released:
            # 이미 끝났거나 없는 슬롯이다. 성공을 돌려주면 "풀었다"고 믿게 된다.
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return RedirectResponse(
            f"/admin?slot={slot_date}", status_code=status.HTTP_303_SEE_OTHER
        )

    @router.post("/admin/accounts/{broker_account_id}/status")
    async def change_status(
        broker_account_id: str, account_status: Annotated[str, Form()]
    ) -> RedirectResponse:
        _reject_unknown(account_status, STATUSES)
        changed = await _require("set_account_status")(broker_account_id, account_status)  # type: ignore[operator]
        return _back_or_missing(changed)

    return router


def _reject_unknown(value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY)


def _back() -> RedirectResponse:
    """Return to the roster so the result is visible, not just reported."""
    return RedirectResponse("/admin/accounts", status_code=status.HTTP_303_SEE_OTHER)


def _back_or_missing(changed: object) -> RedirectResponse:
    # 없는 계좌에 성공을 돌려주지 않는다 — 오타 하나가 "바꿨다"로 보이면
    # 안 바뀐 계좌를 계속 믿게 된다.
    if not changed:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return _back()

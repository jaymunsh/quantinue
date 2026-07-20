"""Order-budget and exposure queries over reflected canonical tables.

런 재개(resume)·시도(attempt) 쿼리들이 같이 살던 파일이었다 — 그 절반은 구
러너와 함께 죽었고, 남은 것은 배분 잡이 타는 일일 주문 예약과 노출 게이트다.
"""

from decimal import Decimal
from typing import Final

from pydantic import TypeAdapter
from sqlalchemy import Table, and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from quantinue.db.contracts import (
    AppOrderExposureReservationOutcome,
    AppOrderExposureReservationResult,
    AppOrderExposureStatus,
    AppOrderExposureSummary,
    DailyOrderReservation,
)

_STRING_ADAPTER = TypeAdapter(str)
_INT_ADAPTER = TypeAdapter(int)
_DECIMAL_ADAPTER = TypeAdapter(Decimal)
_ZERO_MONEY: Final = Decimal("0.00")
_ELIGIBLE_APP_ORDER_STATUSES: Final = (
    AppOrderExposureStatus.PLANNED.value,
    AppOrderExposureStatus.SUBMITTED.value,
    AppOrderExposureStatus.FILLED.value,
)
_TERMINAL_APP_ORDER_STATUSES: Final = (
    AppOrderExposureStatus.FILLED.value,
    AppOrderExposureStatus.FAILED.value,
    AppOrderExposureStatus.CANCELED.value,
)


async def reserve_daily_order(
    connection: AsyncConnection,
    orders: Table,
    signals: Table,
    request: DailyOrderReservation,
) -> AppOrderExposureReservationResult:
    """Reserve an idempotent app order under account-wide and daily limits."""
    await _lock_order_budget(connection, f"capital-cap:{request.account_id}")
    await _lock_order_budget(
        connection, f"daily-order:{request.account_id}:{request.trade_date.isoformat()}"
    )
    await _lock_order_budget(connection, f"order-identity:{request.idempotency_key}")
    existing = (
        (
            await connection.execute(
                select(orders).where(orders.c.idempotency_key == request.idempotency_key)
            )
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        summary = await app_order_exposure_summary(
            connection,
            orders,
            request.account_id,
            request.max_app_order_exposure_usd,
        )
        outcome = (
            AppOrderExposureReservationOutcome.REPLAYED
            if _same_order_reservation(existing, request)
            else AppOrderExposureReservationOutcome.REJECTED
        )
        return AppOrderExposureReservationResult(outcome=outcome, summary=summary)
    count = await connection.scalar(
        select(func.count())
        .select_from(orders.join(signals, orders.c.signal_id == signals.c.id))
        .where(
            and_(
                orders.c.account_id == request.account_id,
                signals.c.trade_date == request.trade_date,
                # 청산은 이 한도의 대상이 아니다. 이 캡은 "하루에 새로 여는
                # 포지션 수"를 제한하려는 것인데, 청산까지 세면 그날 판 만큼
                # 살 수 있는 칸이 사라진다 — 리스크를 줄이는 행동이 리스크를
                # 줄이는 다음 행동을 막는 셈이라 방향이 거꾸로다.
                orders.c.order_type == "bracket",
            )
        )
    )
    if int(count or 0) >= request.cap:
        return AppOrderExposureReservationResult(
            outcome=AppOrderExposureReservationOutcome.REJECTED,
            summary=await app_order_exposure_summary(
                connection,
                orders,
                request.account_id,
                request.max_app_order_exposure_usd,
            ),
        )
    summary = await app_order_exposure_summary(
        connection,
        orders,
        request.account_id,
        request.max_app_order_exposure_usd,
    )
    if summary.planned_or_reserved + request.reference_notional > summary.cap:
        return AppOrderExposureReservationResult(
            outcome=AppOrderExposureReservationOutcome.REJECTED,
            summary=summary,
        )
    _ = await connection.execute(
        insert(orders).values(
            signal_id=request.signal_id,
            account_id=request.account_id,
            ticker=request.ticker,
            quantity=request.quantity,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            take_profit_price=request.take_profit_price,
            status="planned",
            idempotency_key=request.idempotency_key,
        )
    )
    return AppOrderExposureReservationResult(
        outcome=AppOrderExposureReservationOutcome.ACQUIRED,
        summary=await app_order_exposure_summary(
            connection,
            orders,
            request.account_id,
            request.max_app_order_exposure_usd,
        ),
    )


async def app_order_exposure_summary(
    connection: AsyncConnection,
    orders: Table,
    account_id: int,
    cap: Decimal,
) -> AppOrderExposureSummary:
    """Read one account's exact eligible planned-order exposure."""
    exposure = await connection.scalar(
        select(
            func.coalesce(func.sum(orders.c.quantity * orders.c.entry_price), _ZERO_MONEY)
        ).where(
            and_(
                orders.c.account_id == account_id,
                orders.c.status.in_(_ELIGIBLE_APP_ORDER_STATUSES),
            )
        )
    )
    planned_or_reserved = _DECIMAL_ADAPTER.validate_python(exposure)
    return AppOrderExposureSummary(
        account_id=account_id,
        cap=cap,
        planned_or_reserved=planned_or_reserved,
        remaining=max(_ZERO_MONEY, cap - planned_or_reserved),
    )


async def reconcile_app_order_exposure(
    connection: AsyncConnection,
    orders: Table,
    idempotency_key: str,
    status: AppOrderExposureStatus,
) -> AppOrderExposureSummary | None:
    """Apply a canonical status once without reopening terminal exposure."""
    account_id = await connection.scalar(
        select(orders.c.account_id).where(orders.c.idempotency_key == idempotency_key)
    )
    if account_id is None:
        return None
    parsed_account_id = _INT_ADAPTER.validate_python(account_id)
    await _lock_order_budget(connection, f"capital-cap:{parsed_account_id}")
    row = (
        (
            await connection.execute(
                select(orders.c.status)
                .where(orders.c.idempotency_key == idempotency_key)
                .with_for_update()
            )
        )
        .mappings()
        .one()
    )
    current_status = _STRING_ADAPTER.validate_python(row["status"])
    if current_status not in _TERMINAL_APP_ORDER_STATUSES:
        _ = await connection.execute(
            orders.update()
            .where(orders.c.idempotency_key == idempotency_key)
            .values(status=status.value)
        )
    return None


async def _lock_order_budget(connection: AsyncConnection, identity: str) -> None:
    """Take one transaction-scoped advisory lock in the documented fixed order."""
    _ = await connection.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(identity, 0)))
    )


def _same_order_reservation(row: RowMapping, request: DailyOrderReservation) -> bool:
    """Compare the immutable durable order identity against one reservation request."""
    return (
        _INT_ADAPTER.validate_python(row["account_id"]) == request.account_id
        and _INT_ADAPTER.validate_python(row["signal_id"]) == request.signal_id
        and _STRING_ADAPTER.validate_python(row["ticker"]) == request.ticker
        and _INT_ADAPTER.validate_python(row["quantity"]) == request.quantity
        and _DECIMAL_ADAPTER.validate_python(row["entry_price"]) == request.entry_price
        and _DECIMAL_ADAPTER.validate_python(row["stop_price"]) == request.stop_price
        and _DECIMAL_ADAPTER.validate_python(row["take_profit_price"]) == request.take_profit_price
    )



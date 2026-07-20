"""Typed durable reads for the PostgreSQL simulated portfolio."""

from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from quantinue.db.simulated_portfolio import (
    MarkSource,
    PortfolioMark,
    SimulatedAccount,
    SimulatedFill,
    SimulatedOrder,
    SimulatedOrderStatus,
    SimulatedPortfolioSnapshot,
    project_portfolio,
)

LOCAL_SIMULATED_ACCOUNT_ID: Final = "quantinue-local-simulated"


class _AccountRow(BaseModel):
    model_config = ConfigDict(strict=True)

    cash: Decimal
    buying_power: Decimal


class _OrderRow(BaseModel):
    model_config = ConfigDict(strict=True)

    order_id: str
    ticker: str
    quantity: int
    reference_price: Decimal
    status: str
    created_at: datetime


class _FillRow(BaseModel):
    model_config = ConfigDict(strict=True)

    fill_id: str
    order_id: str
    ticker: str
    quantity: int
    price: Decimal
    filled_at: datetime


class _MarkRow(BaseModel):
    model_config = ConfigDict(strict=True)

    ticker: str
    price: Decimal
    # 일봉의 사실은 세션 날짜다 — 시각을 지어내지 않고 자정 UTC로 승격만 한다.
    as_of: date

    @property
    def as_of_datetime(self) -> datetime:
        return datetime.combine(self.as_of, time(), tzinfo=UTC)


async def read_simulated_portfolio(
    engine: AsyncEngine,
    metadata: MetaData,
    opening_cash: Decimal,
    account_identity: str = LOCAL_SIMULATED_ACCOUNT_ID,
) -> SimulatedPortfolioSnapshot:
    """Project canonical account, order, fill, and daily-bar mark rows."""
    accounts = _table(metadata, "tb_account")
    orders = _table(metadata, "tb_order")
    fills = _table(metadata, "tb_fill")
    signals = _table(metadata, "tb_strategist_signals")
    bars = _table(metadata, "tb_daily_bar")
    async with engine.connect() as connection:
        account = _AccountRow.model_validate(
            dict(
                (
                    await connection.execute(
                        select(accounts.c.cash, accounts.c.buying_power).where(
                            accounts.c.broker_account_id == account_identity
                        )
                    )
                )
                .mappings()
                .one()
            )
        )
        order_rows = (
            await connection.execute(
                select(
                    func.coalesce(orders.c.broker_order_id, orders.c.idempotency_key).label(
                        "order_id"
                    ),
                    orders.c.ticker,
                    orders.c.quantity,
                    orders.c.entry_price.label("reference_price"),
                    orders.c.status,
                    signals.c.cycle_ts.label("created_at"),
                )
                .select_from(
                    orders.join(accounts, orders.c.account_id == accounts.c.id).join(
                        signals, orders.c.signal_id == signals.c.id
                    )
                )
                .where(accounts.c.broker_account_id == account_identity)
                .order_by(orders.c.created_at, orders.c.id)
            )
        ).mappings()
        fill_rows = (
            await connection.execute(
                select(
                    fills.c.broker_fill_id.label("fill_id"),
                    func.coalesce(orders.c.broker_order_id, orders.c.idempotency_key).label(
                        "order_id"
                    ),
                    orders.c.ticker,
                    fills.c.quantity,
                    fills.c.price,
                    fills.c.filled_at,
                )
                .select_from(
                    fills.join(orders, fills.c.order_id == orders.c.id).join(
                        accounts, orders.c.account_id == accounts.c.id
                    )
                )
                .where(accounts.c.broker_account_id == account_identity)
                .order_by(fills.c.filled_at, fills.c.id)
            )
        ).mappings()
        # mark는 일봉 종가다. 구 코드는 완료된 런의 판단 시점 시세를 썼는데
        # (pipeline_runs 조인) 러너가 죽어 그 소스는 더 이상 갱신되지 않는다.
        # 일봉은 잡이 매일 채우는 원장이고, D8 계좌 평가와 같은 값이라 웹
        # 포트폴리오와 계좌 곡선이 서로 다른 숫자를 말하지 않는다.
        # 이 계좌가 거래한 종목의 봉만 본다 — 원장에는 유니버스 전체(2000종목,
        # 수십만 봉)가 있고 mark가 필요한 것은 보유 몇 개뿐이다.
        traded = (
            select(orders.c.ticker)
            .join(accounts, orders.c.account_id == accounts.c.id)
            .where(accounts.c.broker_account_id == account_identity)
            .distinct()
            .scalar_subquery()
        )
        mark_rows = (
            await connection.execute(
                select(
                    bars.c.ticker,
                    bars.c.close.label("price"),
                    bars.c.trade_date.label("as_of"),
                )
                .where(bars.c.ticker.in_(traded))
                .distinct(bars.c.ticker)
                .order_by(bars.c.ticker, bars.c.trade_date.desc())
            )
        ).mappings()
    parsed_orders = tuple(_OrderRow.model_validate(dict(row)) for row in order_rows)
    parsed_fills = tuple(_FillRow.model_validate(dict(row)) for row in fill_rows)
    parsed_marks = tuple(_MarkRow.model_validate(dict(row)) for row in mark_rows)
    projected = project_portfolio(
        opening_cash,
        tuple(
            SimulatedOrder(
                order_id=row.order_id,
                ticker=row.ticker,
                quantity=row.quantity,
                reference_price=row.reference_price,
                status=SimulatedOrderStatus(row.status),
                created_at=row.created_at,
            )
            for row in parsed_orders
        ),
        tuple(
            SimulatedFill(
                fill_id=row.fill_id,
                order_id=row.order_id,
                ticker=row.ticker,
                quantity=row.quantity,
                price=row.price,
                filled_at=row.filled_at,
            )
            for row in parsed_fills
        ),
        tuple(
            PortfolioMark(
                ticker=row.ticker,
                price=row.price,
                source=MarkSource.DAILY_BAR_CLOSE,
                as_of=row.as_of_datetime,
            )
            for row in parsed_marks
        ),
    )
    market_value = sum(
        (position.market_value for position in projected.positions), start=Decimal(0)
    )
    durable_account = SimulatedAccount(
        opening_cash=opening_cash,
        current_cash=account.cash,
        equity=account.cash + market_value,
        buying_power=account.buying_power,
    )
    return replace(projected, account=durable_account)


def _table(metadata: MetaData, name: str) -> Table:
    return metadata.tables[name]

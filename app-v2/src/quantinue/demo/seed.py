"""Deterministic demo ledger seed for the filming runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from quantinue.broker.mock import MockBroker
from quantinue.broker.provider import OrderPlan
from quantinue.core.ontology import FillSide
from quantinue.core.order_identity import derive_client_order_id
from quantinue.db.contracts import (
    AppOrderExposureReservationOutcome,
    DailyOrderReservation,
)
from quantinue.db.domain_records import (
    AccountWrite,
    CompletedFillWrite,
    CriticVerdictWrite,
    DailyBarWrite,
    DailyPickWrite,
    StrategistSignalWrite,
)
from quantinue.db.postgres import PostgresRunStore
from quantinue.db.users import UserWrite
from quantinue.demo.scripted_market import DemoScenarioError
from quantinue.roles.role_01_universe_screener.contracts import (
    UniverseMember,
    UniverseScreenerOutput,
)

if TYPE_CHECKING:
    from datetime import date, datetime

_RUN_ID = "demo-seed"


@dataclass(frozen=True, slots=True)
class DemoListing:
    """One tradable demo ticker: universe row + daily-pick scope.

    ``reference``는 이 티커의 봉 가격(시가·종가)이다. 각본 감시 가격과
    어긋나면 배분 매수 직후 방어선이 오발동한다(실측 — 후보 종목이 봉 100 대비
    감시가 55로 잡혀 즉시 손절됐다). 각본 시세의 시작가와 맞춘다.
    """

    ticker: str
    company: str
    sector: str
    reference: Decimal = Decimal("100.00")


@dataclass(frozen=True, slots=True)
class HeldPosition:
    """One seeded bracket holding: S2 방어와 S4 반전 매도의 출발 상태."""

    listing: DemoListing
    quantity: int
    entry: Decimal
    stop: Decimal
    take: Decimal


@dataclass(frozen=True, slots=True)
class DemoUser:
    """One login to create; the password hash is computed by the launcher."""

    login_id: str
    display_name: str
    role: str
    password_hash: str
    owns_account: bool = False


@dataclass(frozen=True, slots=True)
class DemoSeedSpec:
    """Everything the S1 opening state needs, declared in one place."""

    trade_date: date
    cycle_ts: datetime
    broker_account_id: str
    opening_cash: Decimal
    inv_type: str
    held: tuple[HeldPosition, ...]
    candidates: tuple[DemoListing, ...]
    users: tuple[DemoUser, ...] = ()
    # 봉을 깔 세션들. 분석 대상 조회(analysis_subjects)와 크리틱의 급등락
    # 게이트는 **직전 세션 이하**의 봉과 그 전 종가를 요구한다 — 당일 봉만
    # 있으면 사건 재판단이 subject_missing으로 조용히 죽는다(실측).
    # 비우면 trade_date 하루만 깐다.
    bar_dates: tuple[date, ...] = ()
    # 각본 주인공. 이어받기 모드에서는 운영 이력의 오늘 픽 수십 종목이 같은
    # 계좌에 함께 배분돼, 지갑이 문턱(최소 현금)에 닿으면 뒤로 밀린 각본
    # 티커가 안 사진다. 주인공에게만 높은 픽 점수를 줘 먼저 집행되게 한다.
    featured: frozenset[str] = frozenset()

    @property
    def opening_cycle_ts(self) -> datetime:
        """Return the timestamp the starting positions were judged at.

        시작 보유는 장이 열리기 전부터 들고 있던 것이다. 재판단이 도는 시각
        (``cycle_ts``)과 겹치면 그 종목은 "오늘 이미 판단했다"로 분류돼
        재판단에서 빠진다.
        """
        return self.cycle_ts - timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class DemoSeedReport:
    """Observable outcome used by the launcher and the rehearsal check."""

    account_id: int
    signal_ids: tuple[int, ...]
    seeded_positions: int


async def seed_demo_ledger(database_url: str, spec: DemoSeedSpec) -> DemoSeedReport:
    """Seed the demo ledger through the same contracts production writes use.

    일일 잡 전체를 돌려 상태를 만드는 대신, 잡들이 쓰는 것과 같은
    repository·MockBroker 계약으로 최소 원장을 직접 쓴다(demo-video-plan.md
    §4-4). 모든 쓰기가 멱등이라 reset 없이 두 번 불러도 원장이 불어나지
    않는다 — 그것이 리허설 동일성 검증의 전제다.
    """
    store = PostgresRunStore(database_url)
    await store.initialize()
    domain = store.domain
    try:
        listings = tuple(held.listing for held in spec.held) + spec.candidates
        await _seed_scope(domain, spec, listings)
        account_id = await _seed_account_and_users(domain, spec)
        signal_ids = await _seed_holdings(store, domain, spec, account_id)
        # 시가평가 → 당일 시작 equity 스냅샷 순서다. 스냅샷이 손익 계산의
        # 분모가 되므로 평가 없이 찍으면 S1 화면의 곡선이 거짓말을 한다.
        _ = await domain.revalue_accounts(spec.trade_date)
        _ = await domain.snapshot_daily_equity(spec.trade_date)
        return DemoSeedReport(
            account_id=account_id,
            signal_ids=signal_ids,
            seeded_positions=len(spec.held),
        )
    finally:
        await store.close()


async def _seed_scope(
    domain: object, spec: DemoSeedSpec, listings: tuple[DemoListing, ...]
) -> None:
    """Write universe, daily picks, and reference bars for every demo ticker."""
    await domain.save_universe(
        UniverseScreenerOutput(
            run_id=_RUN_ID,
            generated_at=spec.cycle_ts,
            members=tuple(
                UniverseMember(
                    as_of_date=spec.trade_date,
                    ticker=listing.ticker,
                    company_name=listing.company,
                    market_cap=1_000_000_000,
                    evidence_ids=(_RUN_ID,),
                )
                for listing in listings
            ),
        )
    )
    await domain.save_daily_picks(
        tuple(
            DailyPickWrite(
                trade_date=spec.trade_date,
                ticker=listing.ticker,
                universe_as_of=spec.trade_date,
                bucket="trend_leader",
                rank=rank,
                sector=listing.sector,
                # 배경 티커가 0.90이 아닌 이유: 픽 점수는 conviction 평균에
                # 투표한다. 0.90이면 미등록 티커(모델 0.60)까지 mean 0.75로
                # 공격형 매수 문턱(0.65)을 넘어 각본 밖 매수가 나간다.
                # 0.50이면 hold·매수·매도 세 구간이 전부 산술적으로 성립한다
                # (scenario_analyzer._strategy_output 주석 참조).
                #
                # 주인공만 0.95를 받는다. 이어받기 모드에서 운영 픽의
                # conviction이 0.87~0.89대라, 각본 매수(0.50 → mean 0.675)가
                # 그 뒤로 밀려 지갑이 빌 때까지 차례가 오지 않았다. 0.95면
                # mean 0.90으로 맨 앞에 선다 — 배경 티커의 산술은 그대로다.
                score=Decimal("0.95") if listing.ticker in spec.featured else Decimal("0.50"),
            )
            for rank, listing in enumerate(listings, start=1)
        )
    )
    entry_by_ticker = {held.listing.ticker: held.entry for held in spec.held}
    await domain.save_daily_bars(
        tuple(
            DailyBarWrite(
                trade_date=bar_date,
                ticker=listing.ticker,
                open=entry_by_ticker.get(listing.ticker, listing.reference),
                high=entry_by_ticker.get(listing.ticker, listing.reference),
                low=entry_by_ticker.get(listing.ticker, listing.reference),
                close=entry_by_ticker.get(listing.ticker, listing.reference),
                volume=1_000_000,
                source=_RUN_ID,
            )
            for bar_date in (spec.bar_dates or (spec.trade_date,))
            for listing in listings
        )
    )


async def _seed_account_and_users(domain: object, spec: DemoSeedSpec) -> int:
    """Create the filming account and its logins; both writes are idempotent."""
    account_id = await domain.save_account(
        AccountWrite(
            broker_account_id=spec.broker_account_id,
            cash=spec.opening_cash,
            equity=spec.opening_cash,
            buying_power=spec.opening_cash,
            inv_type=spec.inv_type,
        )
    )
    for user in spec.users:
        user_id = await domain.save_user(
            UserWrite(
                login_id=user.login_id,
                display_name=user.display_name,
                role=user.role,
                password_hash=user.password_hash,
            )
        )
        if user.owns_account:
            _ = await domain.set_account_owner(spec.broker_account_id, user_id)
    return account_id


async def _seed_holdings(
    store: PostgresRunStore,
    domain: object,
    spec: DemoSeedSpec,
    account_id: int,
) -> tuple[int, ...]:
    """Book each held position with the allocation job's exact write order.

    예약 → 브로커 → 체결 순서를 그대로 쓴다 — 브로커가 체결한 뒤 원장
    자리가 없는 상태를 만들지 않는 순서이고, idempotency key가 같으므로
    재실행은 중복 주문 대신 no-op이 된다.
    """
    signal_ids: list[int] = []
    broker = MockBroker()
    for held in spec.held:
        signal_id = await domain.save_signal(
            StrategistSignalWrite(
                run_id=_RUN_ID,
                trade_date=spec.trade_date,
                ticker=held.listing.ticker,
                # 재판단 시각보다 **앞선** 시각에 앉힌다. 장중 재판단은
                # 같은 cycle_ts의 판단을 "이미 끝난 것"으로 보고 건너뛰므로
                # (completed_intraday_tickers), 시드가 그 시각을 쓰면 보유
                # 종목의 재판단이 통째로 막힌다 — 실측: 악재 반전 매도(S4)의
                # 공격형 판단이 이 이유로 영영 안 나왔다. 서사로도 이쪽이
                # 맞다: 시작 보유는 "이미 들고 있던 것"이지 지금 산 것이 아니다.
                cycle_ts=spec.opening_cycle_ts,
                side="buy",
                conviction=Decimal("0.800"),
                summary="시작 보유 포지션",
                decision_close=held.entry,
                evidence=(_RUN_ID,),
                inv_type=spec.inv_type,
            )
        )
        signal_ids.append(signal_id)
        _ = await domain.save_verdict(
            CriticVerdictWrite(
                signal_id=signal_id,
                ticker=held.listing.ticker,
                decision="pass",
                category="demo_seed",
                objection="시작 상태 승인",
                confidence=Decimal("0.800"),
                decided_layer="gate",
            )
        )
        client_order_id = derive_client_order_id(
            account_id=account_id, signal_id=signal_id
        )
        reserved = await store.reserve_daily_new_order(
            DailyOrderReservation(
                account_id=account_id,
                trade_date=spec.trade_date,
                signal_id=signal_id,
                idempotency_key=client_order_id,
                ticker=held.listing.ticker,
                quantity=held.quantity,
                entry_price=held.entry,
                stop_price=held.stop,
                take_profit_price=held.take,
                cap=len(spec.held),
                max_app_order_exposure_usd=spec.opening_cash,
            )
        )
        if reserved.outcome is AppOrderExposureReservationOutcome.REJECTED:
            msg = f"seed reservation rejected for {held.listing.ticker}"
            raise DemoScenarioError(msg)
        result = await broker.submit(
            OrderPlan(
                ticker=held.listing.ticker,
                client_order_id=client_order_id,
                quantity=held.quantity,
                entry_price=float(held.entry),
                stop_loss=float(held.stop),
                take_profit=float(held.take),
            )
        )
        _ = await domain.record_completed_fill(
            CompletedFillWrite(
                idempotency_key=client_order_id,
                broker_order_id=result.order_id,
                broker_fill_id=f"{result.order_id}-fill",
                quantity=result.quantity,
                price=Decimal(str(result.filled_avg_price)),
                filled_at=spec.cycle_ts,
                side=FillSide.BUY,
            )
        )
    return tuple(signal_ids)

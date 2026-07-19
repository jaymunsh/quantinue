"""PostgreSQL persistence dedicated to delayed T+5 reviews."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import MetaData, Table, and_, case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from quantinue.roles.analysis.contracts import analysis_run_id
from quantinue.roles.role_11_reviewer.processor import DueReviewSignal, ReviewSnapshotWrite

_TABLES = (
    "pipeline_runs",
    "tb_strategist_signals",
    "tb_order",
    "tb_fill",
    "tb_review_price_snapshots",
    "tb_review",
)


class _SignalRow(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int
    # 러너 행이 없는 잡 판단에서는 NULL이다 — 그때 analysis_run_id로 복원한다.
    run_id: str | None
    inv_type: str
    ticker: str
    side: str
    trade_date: date
    decision_close: Decimal


class _SnapshotRow(BaseModel):
    model_config = ConfigDict(strict=True)
    day_offset: int
    close: Decimal | None = None


class PostgresReviewRepository:
    """Idempotent snapshot and final-review repository."""

    def __init__(self, database_url: str) -> None:
        """Create a lazy async engine."""
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self._metadata = MetaData()

    async def initialize(self) -> None:
        """Reflect review tables after schema bootstrap."""
        async with self._engine.begin() as connection:
            await connection.run_sync(self._metadata.reflect, only=_TABLES)

    async def close(self) -> None:
        """Dispose the connection pool."""
        await self._engine.dispose()

    async def get_signal(self, signal_id: int) -> DueReviewSignal | None:
        """Load a review projection for traded and no-trade signals.

        ``pipeline_runs``와의 조인이 **내부 조인**이었다. 구 11단계 러너만 그
        테이블에 행을 쓰므로, 잡이 만든 판단은 전부 여기서 조용히 탈락했다 —
        실 dev DB에서 잡 판단 91건 중 매칭 0건이었다. T+5 리뷰 API가 새
        파이프라인의 어떤 판단도 채점할 수 없는 상태였다는 뜻이다.

        실행 정체성은 이제 판단 자신에게서 온다: 러너 행이 있으면 그 run_id를
        쓰고, 없으면 분석 잡이 쓰는 것과 **같은 공식**으로 다시 계산한다
        (``analysis_run_id``). 지어내는 것이 아니라 결정적으로 복원하는 것이라
        계보 문자열이 원래 실행과 일치한다.
        """
        signals, runs = self._table("tb_strategist_signals"), self._table("pipeline_runs")
        orders, fills = self._table("tb_order"), self._table("tb_fill")
        fill_base = (
            select(
                orders.c.signal_id.label("signal_id"),
                (func.sum(fills.c.price * fills.c.quantity) / func.sum(fills.c.quantity)).label(
                    "fill_price"
                ),
            )
            .join(fills, fills.c.order_id == orders.c.id)
            .group_by(orders.c.signal_id)
            .subquery()
        )
        query = (
            select(
                signals.c.id,
                runs.c.run_id,
                signals.c.inv_type,
                signals.c.ticker,
                signals.c.side,
                signals.c.trade_date,
                # 매수는 **체결가**로 채점한다 — 실제로 치른 값이 기준이다.
                # 다만 체결이 없으면 판단 시점 종가로 되돌아간다. 사지 않은
                # 매수 제안이야말로 "샀으면 어땠나"를 물어야 하는 대상인데,
                # 여기서 NULL이 나오면 리뷰가 예외로 죽었다(docstring은 줄곧
                # no-trade 신호를 지원한다고 적혀 있었다). 배분이 산 것은
                # 후보의 일부뿐이라 이 갈래가 다수다.
                case(
                    (
                        signals.c.side == "buy",
                        func.coalesce(fill_base.c.fill_price, signals.c.decision_close),
                    ),
                    else_=signals.c.decision_close,
                ).label("decision_close"),
            )
            .outerjoin(
                runs, and_(runs.c.ticker == signals.c.ticker, runs.c.cycle_ts == signals.c.cycle_ts)
            )
            .outerjoin(fill_base, fill_base.c.signal_id == signals.c.id)
        )
        async with self._engine.connect() as connection:
            raw = (
                (await connection.execute(query.where(signals.c.id == signal_id)))
                .mappings()
                .one_or_none()
            )
        if raw is None:
            return None
        row = _SignalRow.model_validate(dict(raw))
        run_id = row.run_id or analysis_run_id(row.trade_date, row.inv_type)
        return DueReviewSignal(
            row.id, run_id, row.ticker, row.side, row.trade_date, row.decision_close
        )

    async def snapshot_offsets(self, signal_id: int) -> frozenset[int]:
        """Return offsets already persisted."""
        table = self._table("tb_review_price_snapshots")
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(table.c.day_offset).where(table.c.signal_id == signal_id)
                )
            ).mappings()
            return frozenset(_SnapshotRow.model_validate(dict(row)).day_offset for row in rows)

    async def save_snapshot(self, value: ReviewSnapshotWrite) -> None:
        """Upsert one official close."""
        table = self._table("tb_review_price_snapshots")
        statement = (
            insert(table)
            .values(
                signal_id=value.signal_id,
                day_offset=value.day_offset,
                price_date=value.price_date,
                close=value.close,
                source=value.source,
                source_ref=value.source_ref,
                observed_at=value.observed_at,
                captured_at=value.captured_at,
                confidence=Decimal(str(value.confidence)),
                evidence_id=value.evidence_id,
                parent_evidence_ids=list(value.parent_evidence_ids),
                model_provider=(
                    value.model_provider.value if value.model_provider is not None else None
                ),
                model_name=value.model_name,
                prompt_version=value.prompt_version,
                policy_version=value.policy_version,
                input_hash=value.input_hash,
            )
            .on_conflict_do_update(
                index_elements=["signal_id", "day_offset"],
                set_={
                    "close": value.close,
                    "source": value.source,
                    "source_ref": value.source_ref,
                    "observed_at": value.observed_at,
                    "captured_at": value.captured_at,
                    "confidence": Decimal(str(value.confidence)),
                    "evidence_id": value.evidence_id,
                    "parent_evidence_ids": list(value.parent_evidence_ids),
                    "model_provider": (
                        value.model_provider.value if value.model_provider is not None else None
                    ),
                    "model_name": value.model_name,
                    "prompt_version": value.prompt_version,
                    "policy_version": value.policy_version,
                    "input_hash": value.input_hash,
                },
                where=table.c.captured_at < value.captured_at,
            )
        )
        async with self._engine.begin() as connection:
            _ = await connection.execute(statement)

    async def finalize_review(self, signal: DueReviewSignal, lesson: str) -> None:
        """Upsert a final review only when all five closes exist."""
        snapshots = self._table("tb_review_price_snapshots")
        async with self._engine.connect() as connection:
            raw = (
                (
                    await connection.execute(
                        select(snapshots.c.day_offset, snapshots.c.close).where(
                            snapshots.c.signal_id == signal.signal_id
                        )
                    )
                )
                .mappings()
                .all()
            )
        rows = tuple(_SnapshotRow.model_validate(dict(row)) for row in raw)
        closes = {row.day_offset: row.close for row in rows if row.close is not None}
        if set(closes) != {1, 2, 3, 4, 5}:
            return
        returns = {
            offset: (close / signal.base_price - 1) * 100 for offset, close in closes.items()
        }
        fields = {
            "ret_1d": returns[1],
            "ret_3d": returns[3],
            "ret_5d": returns[5],
            "is_hit": returns[5] > 0 if signal.side == "buy" else returns[5] <= 0,
            "max_drawdown": min(Decimal(0), *returns.values()),
            "lesson": lesson,
        }
        table = self._table("tb_review")
        statement = (
            insert(table)
            .values(signal_id=signal.signal_id, **fields)
            .on_conflict_do_update(index_elements=["signal_id"], set_=fields)
        )
        # 결과의 durable 기록은 tb_review 한 곳이다. 예전에는 여기서
        # pipeline_runs.payload에도 리뷰를 되썼는데, 그건 구 관제실의 role 11
        # 패널을 채우기 위한 것이었고 화면과 러너가 함께 죽었다. 잡이 만든
        # 판단에는 애초에 그 행이 없어 조건문이 늘 건너뛰던 갈래이기도 하다.
        async with self._engine.begin() as connection:
            _ = await connection.execute(statement)

    def _table(self, name: str) -> Table:
        return self._metadata.tables[name]

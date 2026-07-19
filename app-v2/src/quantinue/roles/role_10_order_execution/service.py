"""Submit one idempotent bracket order through the broker boundary."""

from dataclasses import dataclass, replace
from decimal import Decimal
from hashlib import sha256
from typing import ClassVar

from quantinue.broker.contracts import TradabilityBroker
from quantinue.broker.mock import MockBroker
from quantinue.broker.provider import Broker, OrderPlan
from quantinue.core.contracts import (
    AccountOrder,
    AccountOrderPlan,
    OrderResult,
    PipelineContext,
)
from quantinue.core.errors import ValidationFailureError
from quantinue.core.ontology import EvidenceKind
from quantinue.core.schemas import Evidence
from quantinue.core.typing import require_value
from quantinue.db.contracts import AppOrderExposureStatus, RunStore
from quantinue.db.simulated_portfolio import (
    SimulatedFill,
    SimulatedOrder,
    SimulatedOrderRecorder,
    SimulatedOrderStatus,
)
from quantinue.roles.role_09_risk_portfolio.evidence import evidence_from_pipeline_traces
from quantinue.roles.role_10_order_execution.contracts import OrderExecutionInput


@dataclass(frozen=True, slots=True)
class OrderExecution:
    """Order adapter consumer with a deterministic client order id."""

    broker: Broker
    store: RunStore
    component: ClassVar[str] = "10"
    name: ClassVar[str] = "주문·체결"

    async def _execute_scalar(self, context: PipelineContext) -> PipelineContext:
        """Legacy single-account path, kept for contexts without per-account plans."""
        quantity = require_value(context.quantity, component=self.component, field_name="quantity")
        stop_loss = require_value(
            context.stop_loss, component=self.component, field_name="stop_loss"
        )
        take_profit = require_value(
            context.take_profit, component=self.component, field_name="take_profit"
        )
        if quantity == 0:
            prefix = "로컬 모의 처리" if isinstance(self.broker, MockBroker) else "브로커 처리"
            return context.add_stage(self.component, self.name, f"{prefix} · 주문 생략, 0주")
        entry_price = require_value(
            context.last_price, component=self.component, field_name="last_price"
        )
        # 거래정지·상장폐지 종목은 브로커에 닿기 전에 막는다. 제출 후 거부되면
        # 체결될 수 없었던 주문이 원장에 남는다.
        if not await self._is_tradable(context.request.ticker):
            # 수량도 0으로 내린다 — 남겨두면 역할 11이 "주문이 있어야 한다"로 읽고
            # 런 전체를 실패시킨다(체결되지 않은 계획은 계획이 아니다).
            return replace(
                context, quantity=0, order_skipped_reason="not_tradable"
            ).add_stage(self.component, self.name, "주문 생략 · 거래 불가 종목(정지·상폐)")
        signal_key = f"{context.request.ticker}:{context.request.cycle_ts.isoformat()}".encode()
        signal_id = context.signal_id or int(sha256(signal_key).hexdigest()[:8], 16) + 1
        account_id = context.account_id or 1
        request = OrderExecutionInput(
            run_id=context.run_id,
            execution_at=context.request.cycle_ts,
            evidence=evidence_from_pipeline_traces(context, ("08", "09")),
            signal_id=signal_id,
            account_id=account_id,
            ticker=context.request.ticker,
            cycle_ts=context.request.cycle_ts,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        plan = OrderPlan(
            ticker=request.ticker,
            client_order_id=request.client_order_id,
            quantity=request.quantity,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )
        broker_order = await self.broker.submit(plan)
        order_status = _app_order_exposure_status(broker_order.status)
        order = broker_order.model_copy(update={"status": order_status.value})
        _ = await self.store.reconcile_app_order_exposure(
            request.client_order_id,
            order_status,
        )
        if isinstance(self.broker, MockBroker) and isinstance(self.store, SimulatedOrderRecorder):
            simulated_status = _simulated_order_status(order.status)
            simulated_order = SimulatedOrder(
                order_id=order.order_id,
                ticker=request.ticker,
                quantity=order.quantity,
                reference_price=Decimal(str(request.entry_price)),
                status=simulated_status,
                created_at=request.execution_at,
            )
            fill = (
                SimulatedFill(
                    fill_id=order.order_id,
                    order_id=order.order_id,
                    ticker=request.ticker,
                    quantity=order.quantity,
                    price=Decimal(str(order.filled_avg_price)),
                    filled_at=request.execution_at,
                )
                if simulated_status is SimulatedOrderStatus.FILLED
                else None
            )
            await self.store.record_simulated_order(simulated_order, fill)
        updated = replace(context, order=order)
        evidence = Evidence(
            evidence_id=f"{context.run_id}:10:order:{order.order_id}",
            run_id=context.run_id,
            source="broker-result",
            source_ref=f"broker://order/{order.order_id}",
            observed_at=context.request.cycle_ts,
            captured_at=context.request.cycle_ts,
            confidence=1.0,
            kind=EvidenceKind.BROKER,
            parent_evidence_ids=(context.evidence_trace[-1].evidence_id,),
        )
        prefix = "로컬 모의 체결" if isinstance(self.broker, MockBroker) else "Alpaca Paper 체결"
        return updated.add_stage(
            self.component,
            self.name,
            f"{prefix} · {order.status}, {order.quantity}주",
            evidence=evidence,
        )

    async def _is_tradable(self, ticker: str) -> bool:
        """Ask the venue whether this symbol accepts orders right now.

        Brokers without the capability are treated as tradable so the guard
        never silently disables execution on an adapter that predates it.
        """
        if not isinstance(self.broker, TradabilityBroker):
            return True
        return await self.broker.is_tradable(ticker)

    def _executable_plans(self, context: PipelineContext) -> tuple[AccountOrderPlan, ...]:
        """Return the plans this broker may actually submit.

        A real broker sits in front of exactly one external account, so
        iterating the internal roster would pile every account's position into
        that one — seven accounts would mean seven times the intended size.
        Fan-out therefore belongs to simulation only.
        """
        plans = tuple(plan for plan in context.account_plans if plan.quantity > 0)
        if not plans:
            return ()
        if isinstance(self.broker, MockBroker):
            return plans
        primary = context.account_id or plans[0].account_id
        return tuple(plan for plan in plans if plan.account_id == primary)[:1]

    async def _submit_one(
        self, context: PipelineContext, plan: AccountOrderPlan
    ) -> tuple[OrderResult, Evidence]:
        """Submit one account's bracket and record its simulated bookkeeping."""
        request = OrderExecutionInput(
            run_id=context.run_id,
            execution_at=context.request.cycle_ts,
            evidence=evidence_from_pipeline_traces(context, ("08", "09")),
            signal_id=plan.signal_id,
            account_id=plan.account_id,
            ticker=context.request.ticker,
            cycle_ts=context.request.cycle_ts,
            quantity=plan.quantity,
            entry_price=plan.entry_price,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
        )
        broker_order = await self.broker.submit(
            OrderPlan(
                ticker=request.ticker,
                client_order_id=request.client_order_id,
                quantity=request.quantity,
                entry_price=request.entry_price,
                stop_loss=request.stop_loss,
                take_profit=request.take_profit,
            )
        )
        order_status = _app_order_exposure_status(broker_order.status)
        order = broker_order.model_copy(update={"status": order_status.value})
        _ = await self.store.reconcile_app_order_exposure(request.client_order_id, order_status)
        if isinstance(self.broker, MockBroker) and isinstance(self.store, SimulatedOrderRecorder):
            simulated_status = _simulated_order_status(order.status)
            simulated_order = SimulatedOrder(
                order_id=order.order_id,
                ticker=request.ticker,
                quantity=order.quantity,
                reference_price=Decimal(str(request.entry_price)),
                status=simulated_status,
                created_at=request.execution_at,
            )
            fill = (
                SimulatedFill(
                    fill_id=order.order_id,
                    order_id=order.order_id,
                    ticker=request.ticker,
                    quantity=order.quantity,
                    price=Decimal(str(order.filled_avg_price)),
                    filled_at=request.execution_at,
                )
                if simulated_status is SimulatedOrderStatus.FILLED
                else None
            )
            await self.store.record_simulated_order(simulated_order, fill)
        evidence = Evidence(
            evidence_id=f"{context.run_id}:10:order:{order.order_id}",
            run_id=context.run_id,
            source="broker-result",
            source_ref=f"broker://order/{order.order_id}",
            observed_at=context.request.cycle_ts,
            captured_at=context.request.cycle_ts,
            confidence=1.0,
            kind=EvidenceKind.BROKER,
            parent_evidence_ids=(context.evidence_trace[-1].evidence_id,),
        )
        return order, evidence

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Submit one bracket per executable account plan."""
        plans = self._executable_plans(context)
        if not plans:
            return await self._execute_scalar(context)
        entry_price = require_value(
            context.last_price, component=self.component, field_name="last_price"
        )
        del entry_price
        if not await self._is_tradable(context.request.ticker):
            return replace(context, quantity=0, order_skipped_reason="not_tradable").add_stage(
                self.component, self.name, "주문 생략 · 거래 불가 종목(정지·상폐)"
            )
        orders: list[AccountOrder] = []
        evidences: list[Evidence] = []
        for plan in plans:
            order, evidence = await self._submit_one(context, plan)
            orders.append(AccountOrder(account_id=plan.account_id, result=order))
            evidences.append(evidence)
        primary = orders[0]
        prefix = "로컬 모의 체결" if isinstance(self.broker, MockBroker) else "Alpaca Paper 체결"
        detail = (
            f"{len(orders)}개 계좌 · "
            + " / ".join(f"a{item.account_id}:{item.result.quantity}주" for item in orders)
            if len(orders) > 1
            else f"{primary.result.status}, {primary.result.quantity}주"
        )
        return replace(
            context, order=primary.result, account_orders=tuple(orders)
        ).add_stage(self.component, self.name, f"{prefix} · {detail}", evidence=evidences[0])

def _app_order_exposure_status(status: str) -> AppOrderExposureStatus:
    match status:
        case "submitted" | "accepted":
            return AppOrderExposureStatus.SUBMITTED
        case "filled":
            return AppOrderExposureStatus.FILLED
        case "canceled":
            return AppOrderExposureStatus.CANCELED
        case "rejected" | "failed":
            return AppOrderExposureStatus.FAILED
        case "planned":
            return AppOrderExposureStatus.PLANNED
        case unexpected:
            field = "broker_order_status"
            raise ValidationFailureError(field, unexpected)


def _simulated_order_status(status: str) -> SimulatedOrderStatus:
    try:
        return SimulatedOrderStatus(status)
    except ValueError:
        field = "simulated_order_status"
        raise ValidationFailureError(field, status) from None

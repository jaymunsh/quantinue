"""Submit one idempotent bracket order through the broker boundary."""

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import ClassVar

from quantinue.broker.provider import Broker, OrderPlan
from quantinue.core.contracts import PipelineContext
from quantinue.core.ontology import EvidenceKind
from quantinue.core.schemas import Evidence
from quantinue.core.typing import require_value
from quantinue.roles.role_09_risk_portfolio.evidence import evidence_from_pipeline_traces
from quantinue.roles.role_10_order_execution.contracts import OrderExecutionInput


@dataclass(frozen=True, slots=True)
class OrderExecution:
    """Order adapter consumer with a deterministic client order id."""

    broker: Broker
    component: ClassVar[str] = "10"
    name: ClassVar[str] = "주문·체결"

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Submit a paper bracket or simulate it in mock mode."""
        quantity = require_value(context.quantity, component=self.component, field_name="quantity")
        stop_loss = require_value(
            context.stop_loss, component=self.component, field_name="stop_loss"
        )
        take_profit = require_value(
            context.take_profit, component=self.component, field_name="take_profit"
        )
        if quantity == 0:
            return context.add_stage(self.component, self.name, "skipped, 0주")
        entry_price = require_value(
            context.last_price, component=self.component, field_name="last_price"
        )
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
        order = await self.broker.submit(plan)
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
        return updated.add_stage(
            self.component, self.name, f"{order.status}, {order.quantity}주", evidence=evidence
        )

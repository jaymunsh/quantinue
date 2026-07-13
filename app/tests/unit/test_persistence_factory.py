from typing import ClassVar

import pytest
from pydantic import SecretStr

import quantinue.orchestration.factory as factory_module
from quantinue.broker.contracts import OrderPlan
from quantinue.broker.reservations import OrderReservations
from quantinue.core.config import BrokerMode, DatabaseMode, Settings
from quantinue.core.contracts import OrderResult
from quantinue.db.postgres import PostgresRunStore


class _CapturingBroker:
    reservations: ClassVar[list[OrderReservations]] = []

    def __init__(self, settings: Settings, *, reservations: OrderReservations) -> None:
        del settings
        self.reservations.append(reservations)

    async def submit(self, plan: OrderPlan) -> OrderResult:
        raise AssertionError(plan)


def test_postgres_alpaca_factory_injects_owned_durable_reservations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _CapturingBroker.reservations.clear()
    monkeypatch.setattr(factory_module, "AlpacaBroker", _CapturingBroker)
    settings = Settings(
        database_mode=DatabaseMode.POSTGRES,
        broker_mode=BrokerMode.ALPACA,
        alpaca_api_key=SecretStr("test-key"),
        alpaca_secret_key=SecretStr("test-secret"),
    )

    _, store = factory_module.build_configured_orchestrator(settings)

    assert isinstance(store, PostgresRunStore)
    assert _CapturingBroker.reservations == [store.order_reservations]

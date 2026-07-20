"""FastAPI response schemas for the health and portfolio surfaces.

구 관제실의 런 뷰 20여 종(ControlRoomRun·StageView·RoleDetailView…)이 살던
파일이다. 그 화면과 러너가 함께 죽어서, 남은 것은 지금 라우트가 실제로
돌려주는 것뿐이다 — 잡 기반 화면의 뷰는 ``api/pipeline_presentation``에 산다.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Safe runtime mode summary."""

    model_config = ConfigDict(frozen=True)

    status: str
    broker_mode: str
    llm_mode: str


class PortfolioAccountView(BaseModel):
    """Local simulated account totals."""

    model_config = ConfigDict(frozen=True)

    opening_cash: Decimal
    current_cash: Decimal
    equity: Decimal
    buying_power: Decimal
    currency: str


class PortfolioPositionView(BaseModel):
    """Marked local simulated holding."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    quantity: int = Field(gt=0)
    average_cost: Decimal
    mark_price: Decimal
    mark_source: str
    mark_as_of: datetime
    market_value: Decimal
    unrealized_pnl: Decimal
    allocation: Decimal


class SimulatedOrderView(BaseModel):
    """Local simulated order row."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    ticker: str
    quantity: int = Field(gt=0)
    reference_price: Decimal
    status: str
    created_at: datetime


class SimulatedFillView(BaseModel):
    """Local simulated fill row."""

    model_config = ConfigDict(frozen=True)

    fill_id: str
    order_id: str
    ticker: str
    quantity: int = Field(gt=0)
    price: Decimal
    filled_at: datetime


class SimulatedPortfolioView(BaseModel):
    """Local portfolio projection."""

    model_config = ConfigDict(frozen=True)

    account: PortfolioAccountView
    positions: tuple[PortfolioPositionView, ...]
    orders: tuple[SimulatedOrderView, ...]
    fills: tuple[SimulatedFillView, ...]
    realized_pnl_label: str

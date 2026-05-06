from enum import Enum
from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import datetime

class TradingStrategy(str, Enum):
    PIVOT_REVERSAL = "Pivot Reversal"
    EMA_CROSSOVER = "EMA Crossover"
    TREND_FOLLOWING = "Trend Following"
    MEAN_REVERSION = "Mean Reversion"
    CHART_PATTERN = "Chart Pattern"
    BREAKOUT = "Breakout"
    SCALPING = "Scalping"
    VWAP_PULLBACK = "VWAP Pullback"
    MANUAL = "Manual"

class TradeStatus(str, Enum):
    PLANNED = "Planned"
    OPEN = "Open"      # Order placed but not yet filled
    FILLED = "Filled"  # Entry filled, now active
    CLOSED = "Closed"  # TP, SL, or manual close hit
    CANCELLED = "Cancelled"

class Transaction(BaseModel):
    symbol: str
    quantity: int
    price: float
    timestamp: str
    rationale: str
    action: str  # BUY or SELL
    order_type: str = "MARKET"  # MARKET, LIMIT, STOP, STOP_LIMIT
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timeframe_analysis: Optional[str] = None  # Summary of multi-TF confluence

class Trade(BaseModel):
    id: Optional[int] = None
    symbol: str
    strategy: TradingStrategy
    action: str  # BUY or SELL
    quantity: int
    
    planned_entry: float
    planned_exit: float
    planned_sl: float
    
    fill_price: Optional[float] = None
    fill_time: Optional[str] = None
    
    exit_price: Optional[float] = None
    end_time: Optional[str] = None
    
    status: TradeStatus = TradeStatus.PLANNED
    rationale: str
    timestamp: str
    
    # IBKR identifiers to link callbacks
    parent_order_id: Optional[int] = None
    tp_order_id: Optional[int] = None
    sl_order_id: Optional[int] = None
    perm_id: Optional[int] = None
    tp_perm_id: Optional[int] = None
    sl_perm_id: Optional[int] = None

class AccountState(BaseModel):
    name: str
    strategy: TradingStrategy = TradingStrategy.MANUAL
    transactions: List[Transaction] = []
    trades: List[Trade] = []

    @field_validator("strategy", mode="before")
    @classmethod
    def validate_strategy(cls, v):
        if v == "" or v is None:
            return TradingStrategy.MANUAL
        # If it's already a valid Enum member, return it
        if isinstance(v, TradingStrategy):
            return v
        # Try to match the string value
        for s in TradingStrategy:
            if s.value == v:
                return s
        # Fallback for old string values or unknown values
        return TradingStrategy.MANUAL

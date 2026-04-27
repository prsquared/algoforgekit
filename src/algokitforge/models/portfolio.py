from pydantic import BaseModel
from typing import List, Optional


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


class AccountState(BaseModel):
    name: str
    strategy: str = ""
    transactions: List[Transaction] = []

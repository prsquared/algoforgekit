import json
import os
import asyncio
import math
from datetime import datetime
from typing import Dict, List, Optional
from ib_async import IB, Future, ContFuture, LimitOrder, StopOrder, StopLimitOrder, MarketOrder, Order, BracketOrder

import random
import atexit

from algokitforge.models.portfolio import Transaction, AccountState

# ---------------------------------------------------------------------------
# Singleton IB connection
# ---------------------------------------------------------------------------
ib_instance = None


def _cleanup_ib():
    global ib_instance
    if ib_instance is not None and ib_instance.isConnected():
        ib_instance.disconnect()
        ib_instance = None


atexit.register(_cleanup_ib)


_ib_lock = asyncio.Lock()

async def get_ib() -> IB:
    global ib_instance
    async with _ib_lock:
        if ib_instance is None or not ib_instance.isConnected():
            ib_instance = IB()
            client_id = int(os.getenv("IB_CLIENT_ID", str(random.randint(1000, 9999))))
            host = os.getenv("IB_HOST", "172.29.192.1")
            port = int(os.getenv("IB_PORT", "7497"))
            await ib_instance.connectAsync(host, port, clientId=client_id, timeout=20)
    return ib_instance


# ---------------------------------------------------------------------------
# Contract helpers — MNQ and MGC only
# ---------------------------------------------------------------------------
ALLOWED_SYMBOLS = {"MNQ", "MGC"}

SYMBOL_CONFIG = {
    "MNQ": {"exchange": "CME", "currency": "USD", "tick_size": 0.25, "point_value": 2.0},
    "MGC": {"exchange": "COMEX", "currency": "USD", "tick_size": 0.10, "point_value": 10.0},
}


def _make_contract(symbol: str) -> ContFuture:
    """Create a continuous front-month futures contract for MNQ or MGC."""
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(f"Only {ALLOWED_SYMBOLS} are allowed, got '{symbol}'")
    cfg = SYMBOL_CONFIG[symbol]
    return ContFuture(
        symbol=symbol,
        exchange=cfg["exchange"],
        currency=cfg["currency"],
    )


async def qualify_contract(symbol: str) -> ContFuture:
    """Qualify a futures contract with IBKR."""
    ib = await get_ib()
    contract = _make_contract(symbol)
    qualified = await ib.qualifyContractsAsync(contract)
    if not qualified:
        raise ValueError(f"Could not qualify contract for {symbol}")
    return qualified[0]


# ---------------------------------------------------------------------------
# Account state persistence
# ---------------------------------------------------------------------------

def load_account_state(name: str) -> AccountState:
    filename = f"{name.lower()}_portfolio.json"
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            data = json.load(f)
            return AccountState(**data)
    return AccountState(name=name)


def save_account_state(state: AccountState):
    filename = f"{state.name.lower()}_portfolio.json"
    with open(filename, 'w') as f:
        f.write(state.model_dump_json(indent=2))


# ---------------------------------------------------------------------------
# Account data
# ---------------------------------------------------------------------------

async def fetch_cash_balance() -> float:
    ib = await get_ib()
    summary = await ib.accountSummaryAsync()
    for s in summary:
        if s.tag == 'TotalCashValue':
            return float(s.value)
    return 0.0


async def fetch_holdings() -> Dict[str, int]:
    ib = await get_ib()
    ib.client.reqPositions()
    await asyncio.sleep(2)
    positions = ib.positions()
    holdings = {}
    for pos in positions:
        if pos.position != 0:
            sym = pos.contract.localSymbol or pos.contract.symbol
            holdings[sym] = int(pos.position)
    return holdings


# ---------------------------------------------------------------------------
# Historical bar data — multi-timeframe candles
# ---------------------------------------------------------------------------

async def fetch_candles(symbol: str, bar_size: str, duration: str) -> List[dict]:
    """Fetch historical candlestick data for a futures contract.

    Args:
        symbol: MNQ or MGC
        bar_size: e.g. '5 mins', '15 mins', '1 hour'
        duration: e.g. '1 D', '2 D', '5 D'

    Returns:
        List of dicts with keys: date, open, high, low, close, volume
    """
    ib = await get_ib()
    contract = await qualify_contract(symbol)

    bars = await ib.reqHistoricalDataAsync(
        contract,
        endDateTime='',
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow='TRADES',
        useRTH=False,
        formatDate=2,
    )

    result = []
    for bar in bars:
        result.append({
            "date": str(bar.date),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": int(bar.volume) if bar.volume else 0,
        })
    return result


async def fetch_multi_timeframe_candles(symbol: str) -> dict:
    """Fetch 5-min, 15-min, and 1-hour candles for a symbol.

    Returns:
        dict with keys '5min', '15min', '1hour', each containing list of candle dicts
    """
    candles_5m = await fetch_candles(symbol, '5 mins', '1 D')
    candles_15m = await fetch_candles(symbol, '15 mins', '2 D')
    candles_1h = await fetch_candles(symbol, '1 hour', '5 D')

    return {
        "5min": candles_5m,
        "15min": candles_15m,
        "1hour": candles_1h,
    }


# ---------------------------------------------------------------------------
# Technical indicators (computed locally from candle data)
# ---------------------------------------------------------------------------

def compute_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Compute RSI from a list of closing prices."""
    if len(closes) < period + 1:
        return [None] * len(closes)

    rsi_values: List[Optional[float]] = [None] * period
    gains = []
    losses = []

    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        rsi_values.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(round(100 - (100 / (1 + rs)), 2))

    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0)
        loss = max(-delta, 0)

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(round(100 - (100 / (1 + rs)), 2))

    return rsi_values


def compute_stochastic(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    k_period: int = 14,
    d_period: int = 3,
) -> dict:
    """Compute Stochastic %K and %D from high, low, close lists."""
    k_values: List[Optional[float]] = []

    for i in range(len(closes)):
        if i < k_period - 1:
            k_values.append(None)
            continue
        window_high = max(highs[i - k_period + 1:i + 1])
        window_low = min(lows[i - k_period + 1:i + 1])
        if window_high == window_low:
            k_values.append(50.0)
        else:
            k_val = ((closes[i] - window_low) / (window_high - window_low)) * 100
            k_values.append(round(k_val, 2))

    # %D = SMA of %K
    d_values: List[Optional[float]] = []
    valid_k = [v for v in k_values if v is not None]
    for i in range(len(k_values)):
        if k_values[i] is None:
            d_values.append(None)
            continue
        idx = len([v for v in k_values[:i + 1] if v is not None])
        if idx < d_period:
            d_values.append(None)
        else:
            recent = [v for v in k_values[max(0, i - d_period + 1):i + 1] if v is not None]
            d_values.append(round(sum(recent) / len(recent), 2))

    return {"percent_k": k_values, "percent_d": d_values}


def compute_ema(closes: List[float], period: int) -> List[Optional[float]]:
    """Compute Exponential Moving Average."""
    if len(closes) < period:
        return [None] * len(closes)

    ema_values: List[Optional[float]] = [None] * (period - 1)
    sma = sum(closes[:period]) / period
    ema_values.append(round(sma, 4))
    multiplier = 2 / (period + 1)

    for i in range(period, len(closes)):
        ema = (closes[i] - ema_values[-1]) * multiplier + ema_values[-1]
        ema_values.append(round(ema, 4))

    return ema_values


async def get_technicals_for_symbol(symbol: str) -> dict:
    """Get full technical analysis data: multi-TF candles + indicators on 5-min."""
    mtf = await fetch_multi_timeframe_candles(symbol)

    # Compute indicators on 5-min timeframe
    candles_5m = mtf["5min"]
    closes = [c["close"] for c in candles_5m]
    highs = [c["high"] for c in candles_5m]
    lows = [c["low"] for c in candles_5m]

    rsi_14 = compute_rsi(closes, 14)
    stoch = compute_stochastic(highs, lows, closes, 14, 3)
    ema_9 = compute_ema(closes, 9)
    ema_21 = compute_ema(closes, 21)

    # Only return the last N values to keep payload manageable
    tail = 30

    def last_n(lst, n=tail):
        return lst[-n:] if len(lst) >= n else lst

    return {
        "symbol": symbol,
        "candles_5min": last_n(candles_5m),
        "candles_15min": last_n(mtf["15min"]),
        "candles_1hour": last_n(mtf["1hour"]),
        "indicators_5min": {
            "rsi_14": last_n(rsi_14),
            "stochastic_k": last_n(stoch["percent_k"]),
            "stochastic_d": last_n(stoch["percent_d"]),
            "ema_9": last_n(ema_9),
            "ema_21": last_n(ema_21),
            "current_close": closes[-1] if closes else None,
            "current_rsi": rsi_14[-1] if rsi_14 else None,
            "current_stoch_k": stoch["percent_k"][-1] if stoch["percent_k"] else None,
            "current_stoch_d": stoch["percent_d"][-1] if stoch["percent_d"] else None,
            "current_ema_9": ema_9[-1] if ema_9 else None,
            "current_ema_21": ema_21[-1] if ema_21 else None,
        },
    }


# ---------------------------------------------------------------------------
# Trade execution — Bracket orders (entry + TP + SL)
# ---------------------------------------------------------------------------

async def execute_bracket_trade(
    name: str,
    symbol: str,
    quantity: int,
    action: str,
    entry_price: float,
    take_profit: float,
    stop_loss: float,
    order_type: str,
    rationale: str,
    timeframe_analysis: str = "",
) -> str:
    """Place a bracket order: entry (limit or stop) + take-profit + stop-loss.

    Args:
        name: Account name
        symbol: MNQ or MGC
        quantity: Number of contracts
        action: BUY or SELL
        entry_price: Limit or stop price for entry
        take_profit: Take-profit price
        stop_loss: Stop-loss price
        order_type: LIMIT, STOP, STOP_LIMIT, or MARKET
        rationale: Trade reasoning
        timeframe_analysis: Multi-TF confluence summary
    """
    ib = await get_ib()
    contract = await qualify_contract(symbol)
    reverse_action = "SELL" if action == "BUY" else "BUY"

    # Build entry order
    if order_type == "LIMIT":
        parent = LimitOrder(action, quantity, entry_price)
    elif order_type == "STOP":
        parent = StopOrder(action, quantity, entry_price)
    elif order_type == "STOP_LIMIT":
        # For stop-limit, use entry_price as both stop and limit
        parent = StopLimitOrder(action, quantity, entry_price, entry_price)
    else:
        parent = MarketOrder(action, quantity)

    parent.transmit = False  # Don't transmit until children are attached

    # Take-profit: limit order in reverse direction
    tp_order = LimitOrder(reverse_action, quantity, take_profit)
    tp_order.transmit = False

    # Stop-loss: stop order in reverse direction
    sl_order = StopOrder(reverse_action, quantity, stop_loss)
    sl_order.transmit = True  # Last child transmits the whole group

    # Place the bracket
    parent_trade = ib.placeOrder(contract, parent)
    await asyncio.sleep(0.2)

    tp_order.parentId = parent_trade.order.orderId
    ib.placeOrder(contract, tp_order)
    await asyncio.sleep(0.2)

    sl_order.parentId = parent_trade.order.orderId
    ib.placeOrder(contract, sl_order)

    # Wait briefly for acknowledgement
    await asyncio.sleep(2)

    # Record the transaction
    state = load_account_state(name)
    state.transactions.append(Transaction(
        symbol=symbol,
        quantity=quantity,
        price=entry_price,
        timestamp=datetime.now().isoformat(),
        rationale=rationale,
        action=action,
        order_type=order_type,
        stop_loss=stop_loss,
        take_profit=take_profit,
        timeframe_analysis=timeframe_analysis,
    ))
    save_account_state(state)

    return (
        f"Bracket order placed for {action} {quantity}x {symbol} @ {entry_price} "
        f"(TP: {take_profit}, SL: {stop_loss}, Type: {order_type}). "
        f"Parent order ID: {parent_trade.order.orderId}"
    )


async def execute_market_trade(
    name: str,
    symbol: str,
    quantity: int,
    action: str,
    take_profit: float,
    stop_loss: float,
    rationale: str,
    timeframe_analysis: str = "",
) -> str:
    """Place a market entry with attached TP and SL."""
    ib = await get_ib()
    contract = await qualify_contract(symbol)
    reverse_action = "SELL" if action == "BUY" else "BUY"

    parent = MarketOrder(action, quantity)
    parent.transmit = False

    tp_order = LimitOrder(reverse_action, quantity, take_profit)
    tp_order.transmit = False

    sl_order = StopOrder(reverse_action, quantity, stop_loss)
    sl_order.transmit = True

    parent_trade = ib.placeOrder(contract, parent)
    await asyncio.sleep(0.2)

    tp_order.parentId = parent_trade.order.orderId
    ib.placeOrder(contract, tp_order)
    await asyncio.sleep(0.2)

    sl_order.parentId = parent_trade.order.orderId
    ib.placeOrder(contract, sl_order)

    # Wait for fill
    for _ in range(50):
        await asyncio.sleep(0.1)
        if parent_trade.orderStatus.status == 'Filled':
            break

    avg_price = parent_trade.orderStatus.avgFillPrice or 0.0

    state = load_account_state(name)
    state.transactions.append(Transaction(
        symbol=symbol,
        quantity=quantity,
        price=avg_price,
        timestamp=datetime.now().isoformat(),
        rationale=rationale,
        action=action,
        order_type="MARKET",
        stop_loss=stop_loss,
        take_profit=take_profit,
        timeframe_analysis=timeframe_analysis,
    ))
    save_account_state(state)

    return (
        f"Market bracket order placed for {action} {quantity}x {symbol} "
        f"(filled @ {avg_price}, TP: {take_profit}, SL: {stop_loss}). "
        f"Parent order ID: {parent_trade.order.orderId}"
    )


# ---------------------------------------------------------------------------
# Current price
# ---------------------------------------------------------------------------

async def fetch_current_price(symbol: str) -> float:
    """Get the current price of a futures contract."""
    ib = await get_ib()
    contract = await qualify_contract(symbol)

    ticker = ib.reqMktData(contract, '', False, False)

    price = 0.0
    for _ in range(40):
        await asyncio.sleep(0.1)
        if ticker.last and not math.isnan(ticker.last) and ticker.last > 0:
            price = ticker.last
            break
        if ticker.close and not math.isnan(ticker.close) and ticker.close > 0:
            price = ticker.close
            break

    ib.cancelMktData(contract)
    return float(price)


# ---------------------------------------------------------------------------
# Open orders
# ---------------------------------------------------------------------------

async def fetch_open_orders() -> List[dict]:
    """Get all open/pending orders."""
    ib = await get_ib()
    trades = ib.openTrades()
    result = []
    for trade in trades:
        result.append({
            "orderId": trade.order.orderId,
            "symbol": trade.contract.symbol,
            "action": trade.order.action,
            "quantity": trade.order.totalQuantity,
            "orderType": trade.order.orderType,
            "status": trade.orderStatus.status,
            "lmtPrice": trade.order.lmtPrice,
            "auxPrice": trade.order.auxPrice,
            "parentId": trade.order.parentId,
        })
    return result


async def cancel_order(order_id: int) -> str:
    """Cancel an open order by ID."""
    ib = await get_ib()
    for trade in ib.openTrades():
        if trade.order.orderId == order_id:
            ib.cancelOrder(trade.order)
            await asyncio.sleep(1)
            return f"Cancel request sent for order {order_id}"
    return f"Order {order_id} not found in open orders"


async def cancel_all_orders() -> str:
    """Cancel all open orders."""
    ib = await get_ib()
    ib.reqGlobalCancel()
    await asyncio.sleep(2)
    return "Global cancel request sent for all open orders"


# ---------------------------------------------------------------------------
# Account report
# ---------------------------------------------------------------------------

async def get_account_report(name: str) -> str:
    balance = await fetch_cash_balance()
    holdings = await fetch_holdings()
    open_orders = await fetch_open_orders()
    state = load_account_state(name)

    report = {
        "name": name,
        "cash_balance": balance,
        "holdings": holdings,
        "open_orders": open_orders,
        "strategy": state.strategy,
        "recent_transactions": [t.model_dump() for t in state.transactions[-10:]],
    }
    return json.dumps(report, indent=2)


async def change_account_strategy(name: str, strategy: str) -> str:
    state = load_account_state(name)
    state.strategy = strategy
    save_account_state(state)
    return f"Strategy updated for {name}."


async def get_account_strategy(name: str) -> str:
    state = load_account_state(name)
    return state.strategy

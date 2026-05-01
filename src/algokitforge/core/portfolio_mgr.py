import json
import os
import sqlite3
import asyncio
import math
import warnings
import logging
import random
import atexit
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
from ib_async import IB, Future, ContFuture, LimitOrder, StopOrder, StopLimitOrder, MarketOrder, Order, BracketOrder, util

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Patch asyncio to allow nested event loops
util.patchAsyncio()

# Suppress noisy pandas FutureWarnings
warnings.filterwarnings("ignore", category=FutureWarning)

from algokitforge.models.portfolio import Transaction, AccountState, Trade, TradingStrategy, TradeStatus
from algokitforge.core.pushover_mgr import pushover_mgr
from algokitforge.core.database import db_mgr

# PatternPy chart-pattern detection
from tradingpatterns.tradingpatterns import (
    detect_head_shoulder,
    detect_multiple_tops_bottoms,
    calculate_support_resistance,
    detect_triangle_pattern,
    detect_wedge,
    detect_channel,
    detect_double_top_bottom,
    detect_trendline,
    find_pivots,
)

# ---------------------------------------------------------------------------
# Singleton IB connection
# ---------------------------------------------------------------------------
ib_instance = None
_ib_lock = asyncio.Lock()
_last_connect_time = 0

def _cleanup_ib():
    global ib_instance
    if ib_instance is not None and ib_instance.isConnected():
        try:
            ib_instance.disconnect()
        except:
            pass
        ib_instance = None

atexit.register(_cleanup_ib)

async def on_trade_filled(trade, fill):
    """Callback for when a trade is filled."""
    try:
        symbol = trade.contract.localSymbol or trade.contract.symbol
        action = fill.execution.side
        qty = fill.execution.shares
        price = fill.execution.avgPrice
        fill_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        perm_id = trade.order.permId
        order_id = trade.order.orderId
        
        logger.info(f"Fill detected: {symbol} {action} {qty} @ {price} (permId: {perm_id}, orderId: {order_id})")
        
        msg_type = "TRADE FILL"
        if trade.order.orderType == 'STP':
            msg_type = "STOP LOSS HIT 🔴"
            db_mgr.update_trade_close(perm_id, price, fill_time, order_id=order_id)
        elif trade.order.orderType == 'LMT' and trade.order.parentId != 0:
            msg_type = "TAKE PROFIT HIT 🟢"
            db_mgr.update_trade_close(perm_id, price, fill_time, order_id=order_id)
        elif trade.order.parentId == 0:
            # Check if this is a manual close (opposite action of an active trade)
            # get_active_trade_by_symbol now includes recently closed-without-price trades
            active_trade = db_mgr.get_active_trade_by_symbol(symbol)
            if active_trade and active_trade.action != action:
                msg_type = "MANUAL CLOSE FILLED 🟠"
                db_mgr.update_trade_close(active_trade.perm_id, price, fill_time)
            else:
                msg_type = "ENTRY FILLED 🔵"
                db_mgr.update_trade_fill(perm_id, price, fill_time, order_id=order_id)

        message = f"{msg_type}\n{action} {qty}x {symbol} @ {price}"
        await pushover_mgr.send_notification(message, title="Execution Alert")
    except Exception as e:
        logger.error(f"Error in on_trade_filled callback: {e}")

async def on_order_status(trade):
    """Callback for order status changes."""
    try:
        status = trade.orderStatus.status
        order_id = trade.order.orderId
        perm_id = trade.order.permId
        
        if status in ('Cancelled', 'ApiCancelled', 'Inactive'):
            logger.info(f"Order status '{status}' detected for {order_id} (permId: {perm_id})")
            # Use identifier-based cancel_trade which handles parent/child relationships in DB
            db_mgr.cancel_trade(perm_id)
            db_mgr.cancel_trade(order_id)
    except Exception as e:
        logger.error(f"Error in on_order_status callback: {e}")

async def start_fill_listener():
    """Start persistent listeners on the singleton IB instance."""
    ib = await get_ib()
    # Clear existing handlers
    ib.execDetailsEvent.clear()
    ib.orderStatusEvent.clear()
    
    ib.execDetailsEvent += lambda t, f: asyncio.create_task(on_trade_filled(t, f))
    ib.orderStatusEvent += lambda t: asyncio.create_task(on_order_status(t))
    logger.info("Persistent execution and status listeners started.")

async def get_ib(force_refresh: bool = False) -> IB:
    global ib_instance, _last_connect_time
    
    try:
        await asyncio.wait_for(_ib_lock.acquire(), timeout=20.0)
    except asyncio.TimeoutError:
        logger.error("Timed out waiting for IB connection lock")
        raise RuntimeError("IB connection lock timeout.")
    
    try:
        now = time.time()
        is_healthy = False
        
        # Check current instance health
        if ib_instance is not None:
            try:
                # Basic check
                if ib_instance.isConnected() and ib_instance.client.isConnected():
                    # If it was connected VERY recently (last 5s), assume it's still healthy
                    # to avoid excessive pinging
                    if now - _last_connect_time < 5.0:
                        is_healthy = True
                    else:
                        # Proactive check
                        await asyncio.wait_for(ib_instance.reqCurrentTimeAsync(), timeout=2.0)
                        is_healthy = True
            except Exception:
                is_healthy = False

        # If we're asked to force refresh but we just connected (< 10s ago) and are healthy, skip it
        if force_refresh and is_healthy and (now - _last_connect_time < 10.0):
            logger.info("Skipping forced refresh as connection is healthy and was established recently.")
            force_refresh = False

        if not is_healthy or force_refresh:
            logger.info(f"Establishing {'fresh' if not force_refresh else 'forced'} IB connection...")
            if ib_instance:
                try: ib_instance.disconnect()
                except: pass
            
            ib_instance = IB()
            client_id = int(os.getenv("IB_CLIENT_ID", str(random.randint(1000, 9999))))
            host = os.getenv("IB_HOST", "172.29.192.1")
            port = int(os.getenv("IB_PORT", "7497"))
            
            await ib_instance.connectAsync(host, port, clientId=client_id, timeout=15)
            _last_connect_time = time.time()
            logger.info(f"Connected to IBKR (Client ID: {client_id})")
            
        return ib_instance
    except Exception as e:
        logger.error(f"IB connection failed: {e}")
        if ib_instance:
            try: ib_instance.disconnect()
            except: pass
            ib_instance = None
        raise
    finally:
        _ib_lock.release()

# ---------------------------------------------------------------------------
# Contract helpers
# ---------------------------------------------------------------------------
_env_symbols = os.getenv("ALLOWED_SYMBOLS", "MNQ")
ALLOWED_SYMBOLS = set(s.strip() for s in _env_symbols.split(",") if s.strip())

SYMBOL_CONFIG = {
    "MNQ": {"exchange": "CME", "currency": "USD", "tick_size": 0.25, "point_value": 2.0},
    "MGC": {"exchange": "COMEX", "currency": "USD", "tick_size": 0.10, "point_value": 10.0},
}

SESSION_CONFIG = {
    "NYSE": {"tz": "America/New_York", "start": (9, 30), "end": (16, 0)},
    "LONDON": {"tz": "America/New_York", "start": (3, 0), "end": (12, 0)},
    "ASIA": {"tz": "America/New_York", "start": (18, 0), "end": (6, 0)},
}

def is_market_session_active() -> bool:
    sessions_env = os.getenv("MARKET_SESSION")
    if not sessions_env:
        return True
    
    enabled_sessions = [s.strip().upper() for s in sessions_env.split(",")]
    now_utc = datetime.now(ZoneInfo("UTC"))
    
    # Basic weekend check (Saturday=5, Sunday=6)
    # Note: Futures trade on Sunday evening, but we follow standard session hours here.
    if now_utc.weekday() >= 5:
        # Allow Sunday evening Globex open (after 6 PM ET)
        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
        if now_et.weekday() == 6 and now_et.hour >= 18:
            pass # Continue to session check
        else:
            return False

    for session_name in enabled_sessions:
        if session_name in SESSION_CONFIG:
            cfg = SESSION_CONFIG[session_name]
            tz = ZoneInfo(cfg["tz"])
            now_local = now_utc.astimezone(tz)
            
            start_time = now_local.replace(hour=cfg["start"][0], minute=cfg["start"][1], second=0, microsecond=0)
            end_time = now_local.replace(hour=cfg["end"][0], minute=cfg["end"][1], second=0, microsecond=0)
            
            if cfg["start"] <= cfg["end"]:
                # Normal intra-day session
                if start_time <= now_local <= end_time:
                    return True
            else:
                # Overnight session (e.g. 18:00 to 06:00)
                if now_local >= start_time or now_local <= end_time:
                    return True
                
    return False

def _make_contract(symbol: str) -> ContFuture:
    base = None
    for s in ALLOWED_SYMBOLS:
        if s in symbol: base = s; break
    if not base: raise ValueError(f"Symbol '{symbol}' not allowed.")
    cfg = SYMBOL_CONFIG[base]
    return ContFuture(symbol=base, exchange=cfg["exchange"], currency=cfg["currency"])

async def qualify_contract(symbol: str) -> ContFuture:
    try:
        ib = await get_ib()
        contract = _make_contract(symbol)
        
        # Try to qualify the continuous future first
        qualified = await asyncio.wait_for(ib.qualifyContractsAsync(contract), timeout=15.0)
        if not qualified:
            logger.warning(f"Could not qualify {symbol} as ContFuture, trying as specific contract...")
            # Fallback: sometimes TWS/Gateway prefers a non-continuous contract for some requests
            contract.includeExpired = False
            qualified = await asyncio.wait_for(ib.qualifyContractsAsync(contract), timeout=15.0)
            
        if not qualified:
            raise ValueError(f"Could not qualify contract for {symbol}")
            
        return qualified[0]
    except (asyncio.TimeoutError, Exception) as e:
        logger.error(f"Contract qualification failed for {symbol}: {e}")
        raise RuntimeError(f"Contract qualification failed: {e}")

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def load_account_state(name: str) -> AccountState:
    filename = f"{name.lower()}_portfolio.json"
    if os.path.exists(filename):
        with open(filename, 'r') as f: return AccountState(**json.load(f))
    return AccountState(name=name)

def save_account_state(state: AccountState):
    filename = f"{state.name.lower()}_portfolio.json"
    with open(filename, 'w') as f: f.write(state.model_dump_json(indent=2))

# ---------------------------------------------------------------------------
# Account Data Tools
# ---------------------------------------------------------------------------

async def fetch_cash_balance() -> float:
    ib = await get_ib()
    try:
        summary = await asyncio.wait_for(ib.accountSummaryAsync(), timeout=10.0)
        for s in summary:
            if s.tag == 'TotalCashValue': return float(s.value)
    except Exception as e: logger.error(f"Error fetching cash balance: {e}")
    return 0.0

async def fetch_holdings() -> Dict[str, dict]:
    for attempt in range(3):
        try:
            ib = await get_ib(force_refresh=(attempt > 0))
            # Trigger updates for positions and orders
            ib.reqPositions()
            ib.reqAllOpenOrders()
            # Wait a brief moment for the network roundtrip to populate local cache
            await asyncio.sleep(1.0)
            
            portfolio = {p.contract.conId: p for p in ib.portfolio()}
            positions = ib.positions()
            open_orders = ib.openTrades()
            holdings = {}
            
            for pos in positions:
                if pos.position != 0:
                    full_sym = pos.contract.localSymbol or pos.contract.symbol
                    base_sym = "Unknown"
                    for s in ALLOWED_SYMBOLS:
                        if s in full_sym: 
                            base_sym = s
                            break
                    
                    # Check for protection orders (Stop Loss and Take Profit)
                    has_sl = any(t.order.orderType == 'STP' and (full_sym in (t.contract.localSymbol or "") or base_sym in (t.contract.symbol or "")) for t in open_orders)
                    has_tp = any(t.order.orderType == 'LMT' and t.order.parentId != 0 and (full_sym in (t.contract.localSymbol or "") or base_sym in (t.contract.symbol or "")) for t in open_orders)
                    
                    p_item = portfolio.get(pos.contract.conId)
                    holdings[full_sym] = {
                        "base_symbol": base_sym,
                        "quantity": int(pos.position),
                        "avg_cost": round(pos.avgCost, 2),
                        "mkt_price": round(p_item.marketPrice, 2) if p_item else 0.0,
                        "unrealized_pnl": round(p_item.unrealizedPNL, 2) if p_item else 0.0,
                        "is_naked": not (has_sl and has_tp),
                        "missing_sl": not has_sl,
                        "missing_tp": not has_tp,
                    }
            return holdings
        except (ConnectionError, RuntimeError, asyncio.TimeoutError) as e:
            logger.error(f"fetch_holdings attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                break
    return {}

async def fetch_open_orders() -> List[dict]:
    for attempt in range(3):
        try:
            ib = await get_ib(force_refresh=(attempt > 0))
            ib.reqAllOpenOrders()
            await asyncio.sleep(1.0)
            
            result = []
            for t in ib.openTrades():
                if t.isDone():
                    continue
                # Filter out IBKR's internal/dummy order IDs if they exist
                if t.order.orderId in (13, 14, 15):
                    continue
                    
                result.append({
                    "orderId": t.order.orderId,
                    "permId": t.order.permId, # Long ID shown in TWS
                    "symbol": t.contract.localSymbol or t.contract.symbol,
                    "action": t.order.action,
                    "quantity": t.order.totalQuantity,
                    "orderType": t.order.orderType,
                    "status": t.orderStatus.status,
                    "lmtPrice": t.order.lmtPrice,
                    "auxPrice": t.order.auxPrice,
                    "parentId": t.order.parentId,
                    "timestamp": t.log[0].time.strftime("%Y-%m-%d %H:%M:%S") if t.log else None
                })
            return result
        except (ConnectionError, RuntimeError, asyncio.TimeoutError) as e:
            logger.error(f"fetch_open_orders attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                break
    return []

# ---------------------------------------------------------------------------
# Technical Analysis
# ---------------------------------------------------------------------------

async def _req_historical_with_error_guard(ib: IB, contract, bar_size: str, duration: str) -> list:
    error_event = asyncio.Event(); error_info = {}
    def _on_error(req_id, code, msg, *args):
        # 162: Historical Market Data Service error
        # 200: No security definition has been found
        # 321: Error validating request
        # 322: Error validating request
        if code in (162, 200, 321, 322): 
            error_info["code"], error_info["msg"] = code, msg
            error_event.set()
            
    ib.errorEvent += _on_error
    try:
        try:
            task = asyncio.ensure_future(ib.reqHistoricalDataAsync(contract, '', duration, bar_size, 'TRADES', False, 2))
        except Exception as e:
            logger.error(f"Error starting historical data request: {e}")
            raise
            
        done, pending = await asyncio.wait([task, asyncio.create_task(error_event.wait())], return_when=asyncio.FIRST_COMPLETED, timeout=45)
        for t in pending: t.cancel()
        
        if error_event.is_set(): 
            # If it's a "no data" error (162), we might want to return [] instead of raising
            if error_info["code"] == 162:
                logger.warning(f"IBKR reported no historical data for {contract.symbol}: {error_info['msg']}")
                return []
            raise RuntimeError(f"IBKR Error {error_info['code']}: {error_info['msg']}")
            
        if task in done:
            return task.result()
        logger.warning(f"Historical data request timed out for {contract.symbol} ({bar_size})")
        return []
    finally: 
        ib.errorEvent -= _on_error

async def fetch_candles(symbol: str, bar_size: str, duration: str) -> List[dict]:
    # Increased attempts and better retry logic
    for attempt in range(3):
        try:
            ib = await get_ib(force_refresh=(attempt > 0))
            contract = await qualify_contract(symbol)
            bars = await _req_historical_with_error_guard(ib, contract, bar_size, duration)
            if not bars:
                logger.warning(f"fetch_candles returned empty list for {symbol} ({bar_size}) on attempt {attempt+1}")
                if attempt < 2:
                    await asyncio.sleep(2)
                    continue
            return [{"date": str(b.date), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": int(b.volume or 0)} for b in bars]
        except Exception as e:
            logger.error(f"fetch_candles attempt {attempt+1} failed for {symbol}: {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                break
    return []

async def fetch_multi_timeframe_candles(symbol: str) -> dict:
    res = await asyncio.gather(fetch_candles(symbol, '2 mins', '1 D'), fetch_candles(symbol, '5 mins', '1 D'), fetch_candles(symbol, '15 mins', '2 D'), fetch_candles(symbol, '1 hour', '5 D'))
    return dict(zip(['2min', '5min', '15min', '1hour'], res))

# Indicators
def compute_rsi(closes, period=14):
    if len(closes) < period + 1: return [None]*len(closes)
    s = pd.Series(closes); delta = s.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return (100 - (100 / (1 + rs))).round(2).tolist()

def compute_ema(closes, period):
    if len(closes) < period: return [None]*len(closes)
    return pd.Series(closes).ewm(span=period, adjust=False).mean().round(4).tolist()

def compute_stochastic(highs, lows, closes, k=14, d=3):
    if len(closes) < k: return {"percent_k": [None]*len(closes), "percent_d": [None]*len(closes)}
    h, l, c = pd.Series(highs), pd.Series(lows), pd.Series(closes)
    pk = 100 * (c - l.rolling(k).min()) / (h.rolling(k).max() - l.rolling(k).min())
    return {"percent_k": pk.round(2).tolist(), "percent_d": pk.rolling(d).mean().round(2).tolist()}

async def get_technicals_for_symbol(symbol: str) -> dict:
    try:
        mtf = await fetch_multi_timeframe_candles(symbol)
        c5 = mtf["5min"]
        if not c5: 
            # If 5min is missing, try to see if ANY timeframe has data to provide a better error
            has_any = any(mtf.values())
            if not has_any:
                return {"error": "No market data available for any timeframe. Check your IBKR subscriptions."}
            return {"error": "5-minute candle data missing, but other timeframes present. Check connection."}
            
        # Indicators and analysis for each timeframe
        cl5, hi5, lo5 = [c["close"] for c in c5], [c["high"] for c in c5], [c["low"] for c in c5]
        rsi5, e9_5, e21_5 = compute_rsi(cl5), compute_ema(cl5, 9), compute_ema(cl5, 21)
        stoch5 = compute_stochastic(hi5, lo5, cl5)
        
        c15 = mtf["15min"]
        cl15 = [c["close"] for c in c15] if c15 else []
        e9_15, e21_15 = compute_ema(cl15, 9), compute_ema(cl15, 21)
        
        c2 = mtf["2min"]
        cl2 = [c["close"] for c in c2] if c2 else []
        e9_2, e21_2 = compute_ema(cl2, 9), compute_ema(cl2, 21)
        
        c1h = mtf["1hour"]

        return {
            "symbol": symbol,
            "timeframe_2min": {
                "candles": c2[-15:] if c2 else [],
                "ema_crossover": detect_ema_crossover(cl2, 9, 21) if cl2 else None
            },
            "timeframe_5min": {
                "candles": c5[-30:],
                "indicators": {"rsi": rsi5[-1], "ema_9": e9_5[-1], "ema_21": e21_5[-1], "stoch_k": stoch5["percent_k"][-1], "stoch_d": stoch5["percent_d"][-1]},
                "structure": detect_pivot_structure(c5),
                "patterns": compute_pattern_analysis(c5)
            },
            "timeframe_15min": {
                "candles": c15[-20:] if c15 else [],
                "indicators": {"ema_9": e9_15[-1] if e9_15 else None, "ema_21": e21_15[-1] if e21_15 else None},
                "structure": detect_pivot_structure(c15) if c15 else None,
                "patterns": compute_pattern_analysis(c15) if c15 else None
            },
            "timeframe_1hour": {
                "candles": c1h[-10:] if c1h else [],
                "structure": detect_pivot_structure(c1h) if c1h else None
            }
        }
    except Exception as e:
        logger.error(f"Error in get_technicals_for_symbol: {e}")
        return {"error": str(e)}

def detect_pivot_structure(candles, lookback=20):
    if len(candles) < 15: return {"trend": "neutral", "pivots": []}
    df = pd.DataFrame(candles).rename(columns={"high": "high", "low": "low", "close": "close"})
    df = find_pivots(df); recent = df.tail(lookback)
    pivots = [{"date": str(idx), "signal": sig} for idx, sig in recent["signal"].items() if sig != ""]
    return {"trend": "bullish" if "HH" in df['signal'].tail(10).values else "bearish", "pivots": pivots}

def compute_pattern_analysis(candles):
    if len(candles) < 15: return {}
    df = pd.DataFrame(candles).rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
    df.index = pd.to_datetime([c["date"] for c in candles])
    try:
        df = detect_head_shoulder(df); df = detect_multiple_tops_bottoms(df); df = calculate_support_resistance(df)
        df = detect_triangle_pattern(df); df = detect_wedge(df); df = detect_channel(df); df = detect_double_top_bottom(df)
        active = []
        for col in ["head_shoulder_pattern", "multiple_top_bottom_pattern", "triangle_pattern", "wedge_pattern", "channel_pattern", "double_pattern"]:
            if col in df.columns:
                vals = df[col].dropna(); vals = vals[vals != ""]
                if not vals.empty: active.append(str(vals.iloc[-1]))
        return {"active_patterns": active, "support": round(df["support"].iloc[-1], 2) if "support" in df.columns else None, "resistance": round(df["resistance"].iloc[-1], 2) if "resistance" in df.columns else None}
    except Exception as e: logger.error(f"Pattern analysis failed: {e}"); return {}

def detect_ema_crossover(closes, fast_period=9, slow_period=21):
    f, s = compute_ema(closes, fast_period), compute_ema(closes, slow_period)
    if len(f) < 2 or f[-1] is None or s[-1] is None: return {"crossover": None}
    prev_f, curr_f = f[-2], f[-1]; prev_s, curr_s = s[-2], s[-1]
    if prev_f <= prev_s and curr_f > curr_s: cross = "bullish"
    elif prev_f >= prev_s and curr_f < curr_s: cross = "bearish"
    else: cross = None
    return {"ema_fast": curr_f, "ema_slow": curr_s, "crossover": cross, "aligned_bullish": curr_f > curr_s}

# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

async def fetch_current_price(symbol: str) -> float:
    for attempt in range(3):
        try:
            ib = await get_ib(force_refresh=(attempt > 0))
            contract = await qualify_contract(symbol)
            ticker = ib.reqMktData(contract, '', False, False)
            price = 0.0
            # Wait for ticker to populate
            for _ in range(40):
                await asyncio.sleep(0.1)
                if ticker.last > 0: price = ticker.last; break
                if ticker.close > 0: price = ticker.close; break
            
            ib.cancelMktData(contract)
            if price > 0:
                return float(price)
            logger.warning(f"Price fetch returned 0 for {symbol} on attempt {attempt+1}")
        except Exception as e:
            logger.error(f"fetch_current_price attempt {attempt+1} failed: {e}")
            if attempt < 2: await asyncio.sleep(1)
    return 0.0

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

async def check_existing_position(symbol: str, allow_scaling: bool = False) -> Optional[str]:
    # 1. Check for filled positions
    holdings = await fetch_holdings()
    for h_sym, data in holdings.items():
        if symbol in h_sym and data["quantity"] != 0:
            if not allow_scaling:
                return f"Existing position in {h_sym}. You must close it before entering a new setup."
            if abs(data["quantity"]) >= 5:
                return f"Max scaling reached for {h_sym} (5 contracts)."
            
    # 2. Check for open orders (pending entries)
    # We ignore child orders (TP/SL) which have a parentId.
    # We only care about pending entry orders.
    open_orders = await fetch_open_orders()
    for o in open_orders:
        if symbol in o["symbol"]:
            if not o.get("parentId"):
                return f"Already have a pending entry order for {symbol} (Order ID: {o['orderId']}). Cancel it first if you want to change your entry."
                
    return None

async def execute_bracket_trade(name, symbol, quantity, action, entry_price, take_profit, stop_loss, order_type, rationale, timeframe_analysis=None, strategy: Optional[str] = None, **kwargs) -> str:
    if not is_market_session_active():
        sessions = os.getenv("MARKET_SESSION")
        msg = f"REJECTED: Outside of enabled market sessions ({sessions})"
        logger.warning(msg)
        return msg

    err = await check_existing_position(symbol, kwargs.get("allow_scaling", False))
    if err: return f"REJECTED: {err}"
    
    orders_sent = False
    for attempt in range(2):
        try:
            ib = await get_ib(force_refresh=(attempt > 0))
            contract = await qualify_contract(symbol)
            rev = "SELL" if action == "BUY" else "BUY"
            
            if order_type == "LIMIT": p = LimitOrder(action, quantity, entry_price, outsideRth=True)
            elif order_type == "STOP": p = StopOrder(action, quantity, entry_price, outsideRth=True)
            elif order_type == "STOP_LIMIT": p = StopLimitOrder(action, quantity, entry_price, entry_price, outsideRth=True)
            else: p = MarketOrder(action, quantity)
            
            p.transmit = False
            tp = LimitOrder(rev, quantity, take_profit, outsideRth=True); tp.transmit = False
            sl = StopOrder(rev, quantity, stop_loss, outsideRth=True); sl.transmit = True
            
            # Place the bracket
            trade = ib.placeOrder(contract, p)
            # -----------------------------------------------------------------------
            # CRITICAL: Once the parent order is placed, we mark it as sent to 
            # prevent the retry loop from double-ordering on connection blips.
            # -----------------------------------------------------------------------
            orders_sent = True 
            
            tp.parentId = trade.order.orderId
            tp_trade = ib.placeOrder(contract, tp)
            sl.parentId = trade.order.orderId
            sl_trade = ib.placeOrder(contract, sl)
            
            # Wait a moment for permIds to be assigned by TWS
            for _ in range(20):
                if trade.order.permId and tp_trade.order.permId and sl_trade.order.permId:
                    break
                await asyncio.sleep(0.1)
                
            # Database Persistence: Use provided strategy if available, otherwise fall back to account default
            if strategy:
                try:
                    strat_enum = TradingStrategy(strategy)
                except ValueError:
                    strat_enum = TradingStrategy.MANUAL
            else:
                current_strategy = await get_account_strategy(name)
                try:
                    strat_enum = TradingStrategy(current_strategy)
                except ValueError:
                    strat_enum = TradingStrategy.MANUAL

            db_trade = Trade(
                symbol=symbol,
                strategy=strat_enum,
                action=action,
                quantity=quantity,
                planned_entry=entry_price if entry_price > 0 else 0.0,
                planned_exit=take_profit,
                planned_sl=stop_loss,
                status=TradeStatus.OPEN,
                rationale=rationale,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                parent_order_id=trade.order.orderId,
                tp_order_id=tp.orderId,
                sl_order_id=sl.orderId,
                perm_id=trade.order.permId or 0,
                tp_perm_id=tp_trade.order.permId or 0,
                sl_perm_id=sl_trade.order.permId or 0
            )
            db_mgr.add_trade(db_trade)

            # JSON Legacy Persistence
            state = load_account_state(name)
            tx = Transaction(
                symbol=symbol,
                quantity=quantity,
                price=entry_price if entry_price > 0 else 0.0,
                action=action,
                rationale=rationale,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                order_type=order_type,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timeframe_analysis=timeframe_analysis
            )
            state.transactions.append(tx)
            state.trades.append(db_trade) # Also store in AccountState
            save_account_state(state)
            
            asyncio.create_task(pushover_mgr.send_notification(f"Placed {action} {symbol}"))
            return f"Bracket placed. OrderID: {trade.order.orderId}, PermID: {trade.order.permId}"
        except Exception as e:
            if orders_sent:
                # If orders were already sent, DO NOT retry. Just report the follow-up error.
                logger.error(f"Orders were SENT but subsequent logic failed: {e}")
                return f"SUCCESS: Bracket placed. OrderID: {trade.order.orderId if 'trade' in locals() else '?'}, PermID: {trade.order.permId if 'trade' in locals() else '?'}, but journal error: {e}"
                
            logger.error(f"execute_bracket_trade attempt {attempt+1} failed: {e}")
            if attempt < 1: await asyncio.sleep(1)
            else: return f"ERROR: {e}"

async def execute_market_trade(name, symbol, quantity, action, take_profit, stop_loss, rationale, timeframe_analysis=None, strategy: Optional[str] = None, **kwargs) -> str:
    return await execute_bracket_trade(name, symbol, quantity, action, 0, take_profit, stop_loss, "MARKET", rationale, timeframe_analysis, strategy, **kwargs)

async def execute_close_position(name, symbol, rationale) -> str:
    for attempt in range(2):
        try:
            ib = await get_ib(force_refresh=(attempt > 0))
            
            # 1. Nuclear option: Cancel ALL open orders globally to clear any orphaned brackets (TP/SL)
            # Since the user only trades one instrument at a time, this is the most reliable way.
            logger.info("Executing nuclear order cancellation...")
            ib.reqGlobalCancel()
            await asyncio.sleep(1.5) # Wait for cancellation to propagate
            
            # 2. Check current holdings after cleanup
            holdings = await fetch_holdings()
            qty = 0
            for h_sym, data in holdings.items():
                if symbol in h_sym:
                    qty = data["quantity"]
                    break
            
            if qty == 0:
                return "All orders cancelled. No active position found to flatten."
            
            # 3. Flatten the remaining position with a Market Order
            contract = await qualify_contract(symbol)
            trade = ib.placeOrder(contract, MarketOrder("SELL" if qty > 0 else "BUY", abs(qty)))
            
            # Update database for manual closure
            active_trade = db_mgr.get_active_trade_by_symbol(symbol)
            if active_trade:
                db_mgr.update_trade_close(active_trade.perm_id, 0.0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            msg = f"Nuclear cleanup: All orders cancelled and market close order sent for {symbol} ({qty} units)."
            logger.info(msg)
            return msg
        except Exception as e:
            logger.error(f"execute_close_position attempt {attempt+1} failed: {e}")
            if attempt < 1: await asyncio.sleep(1)
            else: return f"ERROR: {e}"

async def cancel_order(order_id: int) -> str:
    """Cancel order(s) matching the given ID (orderId, permId, or parentId)."""
    for attempt in range(2):
        try:
            ib = await get_ib(force_refresh=(attempt > 0))
            ib.reqAllOpenOrders()
            await asyncio.sleep(1.5)
            
            to_cancel = []
            for t in ib.openTrades():
                # Match by session orderId, IBKR permId, or parentId (for brackets)
                if t.order.orderId == order_id or t.order.permId == order_id or t.order.parentId == order_id:
                    to_cancel.append(t)
            
            if not to_cancel:
                # If not found in openTrades, try to see if it's in the broader trades list
                for t in ib.trades():
                    if (t.order.orderId == order_id or t.order.permId == order_id or t.order.parentId == order_id) and not t.isDone():
                        to_cancel.append(t)

            if not to_cancel:
                return f"Order {order_id} not found in open orders."

            cancelled_info = []
            errors = []
            
            def on_error(reqId, errorCode, errorString, contract=None):
                if errorCode in (10147, 135, 161, 201, 202): # Common order errors
                    errors.append(f"IBKR Error {errorCode}: {errorString}")

            ib.errorEvent += on_error
            try:
                for t in to_cancel:
                    logger.info(f"Requesting cancellation for: oID:{t.order.orderId}/pID:{t.order.permId} (Status: {t.orderStatus.status})")
                    ib.cancelOrder(t.order)
                    cancelled_info.append(f"oID:{t.order.orderId}/pID:{t.order.permId}")
                    # Brief wait between requests to ensure they are sent
                    await asyncio.sleep(0.2)
                
                # Wait for TWS to process and potentially return errors
                await asyncio.sleep(2.0)
            finally:
                ib.errorEvent -= on_error
            
            if errors:
                return f"Cancellation sent for {cancelled_info}, but IBKR reported errors: {'; '.join(errors)}"
            
            return f"Cancellation request sent for orders: {cancelled_info}. Check TWS or your holdings to confirm."
        except Exception as e:
            logger.error(f"cancel_order attempt {attempt+1} failed: {e}")
            if attempt < 1: await asyncio.sleep(1)
            else: return f"ERROR: {e}"

async def cancel_all_orders() -> str:
    ib = await get_ib(); ib.reqGlobalCancel(); return "Global cancel sent"

async def modify_order_prices(order_id, lmt_price=None, aux_price=None) -> str:
    for attempt in range(2):
        try:
            ib = await get_ib(force_refresh=(attempt > 0))
            ib.reqAllOpenOrders()
            await asyncio.sleep(1.0)
            for t in ib.openTrades():
                # Support modification by session orderId or IBKR permId
                if t.order.orderId == order_id or t.order.permId == order_id:
                    if lmt_price: t.order.lmtPrice = lmt_price
                    if aux_price: t.order.auxPrice = aux_price
                    ib.placeOrder(t.contract, t.order)
                    return f"Modified order (oID:{t.order.orderId}/pID:{t.order.permId})"
            return f"Order {order_id} not found or already closed."
        except Exception as e:
            logger.error(f"modify_order_prices attempt {attempt+1} failed: {e}")
            if attempt < 1: await asyncio.sleep(1)
            else: return f"ERROR: {e}"

async def get_account_report(name: str) -> str:
    return json.dumps({"balance": await fetch_cash_balance(), "holdings": await fetch_holdings(), "orders": await fetch_open_orders()}, indent=2)

async def change_account_strategy(name, strategy):
    try:
        strat_enum = TradingStrategy(strategy)
    except ValueError:
        return f"Invalid strategy. Choose from: {[s.value for s in TradingStrategy]}"
    
    s = load_account_state(name)
    s.strategy = strat_enum
    save_account_state(s)
    return f"Strategy updated to {strat_enum.value}"

async def get_account_strategy(name):
    return load_account_state(name).strategy

async def get_trades_report(name: str) -> str:
    """Retrieve all trades from the database for the given account."""
    # Note: Currently db_mgr stores all trades globally. 
    # We could filter by account if needed in the future.
    with sqlite3.connect(db_mgr.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        trades = [dict(row) for row in rows]
    return json.dumps(trades, indent=2)

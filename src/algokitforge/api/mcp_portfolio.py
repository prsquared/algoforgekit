import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import json
from mcp.server.fastmcp import FastMCP
from algokitforge.core.portfolio_mgr import (
    get_ib,
    fetch_cash_balance,
    fetch_holdings,
    fetch_current_price,
    fetch_candles,
    fetch_multi_timeframe_candles,
    get_technicals_for_symbol,
    execute_bracket_trade,
    execute_market_trade,
    execute_close_position,
    fetch_open_orders,
    cancel_order,
    cancel_all_orders,
    modify_order_prices,
    get_account_report,
    change_account_strategy,
    get_account_strategy,
    ALLOWED_SYMBOLS,
    compute_pattern_analysis,
    detect_pivot_structure,
    detect_ema_crossover,
    compute_ema,
)

mcp = FastMCP("ibkr_day_trader")


# ---------------------------------------------------------------------------
# Account tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_balance(name: str) -> float:
    """Get the cash balance of the trading account.

    Args:
        name: The name of the account holder
    """
    return await fetch_cash_balance()


@mcp.tool()
async def get_holdings(name: str) -> str:
    """Get current open positions/holdings in the account.

    Args:
        name: The name of the account holder
    """
    holdings = await fetch_holdings()
    return json.dumps(holdings, indent=2)


# ---------------------------------------------------------------------------
# Market data tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_price(symbol: str) -> float:
    """Get the current real-time price of the futures symbol.

    Args:
        symbol: The futures symbol — e.g. 'MNQ' or 'MGC'
    """
    return await fetch_current_price(symbol)


@mcp.tool()
async def get_candles(symbol: str, bar_size: str, duration: str) -> str:
    """Fetch historical candlestick (OHLCV) data for MNQ or MGC.

    Args:
        symbol: The futures symbol — e.g. 'MNQ' or 'MGC'
        bar_size: Bar size — use '2 mins', '5 mins', '15 mins', or '1 hour'
        duration: Duration — use '1 D', '2 D', or '5 D'
    """
    candles = await fetch_candles(symbol, bar_size, duration)
    return json.dumps(candles, indent=2)


@mcp.tool()
async def get_full_technicals(symbol: str) -> str:
    """Get complete technical analysis data for a symbol: multi-timeframe candles
    (2-min, 5-min, 15-min, 1-hour) plus RSI(14), Stochastic(14,3), EMA(9), EMA(21)
    computed on the 5-minute timeframe. Also includes pivot structure (HH/HL/LH/LL),
    EMA crossover detection, and PatternPy chart patterns on 5-min and 15-min.
    Use this as your PRIMARY analysis tool before considering any trade.

    Args:
        symbol: The futures symbol — e.g. 'MNQ' or 'MGC'
    """
    data = await get_technicals_for_symbol(symbol)
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_pattern_analysis(symbol: str, timeframe: str = "5min") -> str:
    """Run PatternPy chart-pattern recognition + pivot structure + EMA crossover
    on the specified timeframe candles for a symbol. Use this for an additional
    layer of confirmation before entering a trade.

    Patterns detected: Head & Shoulders, Inverse H&S, Multiple Tops/Bottoms,
    Ascending/Descending Triangles, Wedges, Channels (Up/Down), Double Top/Bottom.

    Pivot structure: identifies HH, HL, LH, LL — and flags whether a confirmed
    reversal break (LH broken for BUY / HL broken for SELL) is present.

    Args:
        symbol:    The futures symbol — e.g. 'MNQ' or 'MGC'
        timeframe: Timeframe to analyze — '2min', '5min', '15min', or '1hour'
    """
    valid_tfs = {"2min": "2 mins", "5min": "5 mins", "15min": "15 mins", "1hour": "1 hour"}
    dur_map   = {"2min": "1 D",  "5min": "1 D",    "15min": "2 D",    "1hour": "5 D"}

    if timeframe not in valid_tfs:
        return json.dumps({"error": f"Invalid timeframe '{timeframe}'. Choose from: {list(valid_tfs)}"})

    candles = await fetch_candles(symbol, valid_tfs[timeframe], dur_map[timeframe])
    closes  = [c["close"] for c in candles]

    patterns  = compute_pattern_analysis(candles)
    pivots    = detect_pivot_structure(candles, lookback=20)
    ema_cross = detect_ema_crossover(closes, fast_period=9, slow_period=21)

    result = {
        "symbol":    symbol,
        "timeframe": timeframe,
        "chart_patterns": patterns,
        "pivot_structure": pivots,
        "ema_crossover":  ema_cross,
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Order execution tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def place_bracket_order(
    name: str,
    symbol: str,
    quantity: int,
    action: str,
    entry_price: float,
    take_profit: float,
    stop_loss: float,
    order_type: str,
    rationale: str,
    timeframe_analysis: str,
    strategy: str = "Manual",
    allow_scaling: bool = False,
) -> str:
    """Place a bracket order with entry + take-profit + stop-loss.
    ALWAYS use this tool for placing trades. Every trade MUST have a TP and SL.

    The entry order can be a LIMIT, STOP, STOP_LIMIT, or MARKET order.
    - Use LIMIT for entries at a better price (buy below / sell above market)
    - Use STOP for breakout entries (buy above / sell below market)
    - Use STOP_LIMIT for precise breakout entries with a price cap
    - Use MARKET only when you need immediate execution

    Strategy Selection:
    - Choose the most appropriate strategy from: 'Pivot Reversal', 'EMA Crossover', 
      'Trend Following', 'Mean Reversion', 'Chart Pattern', 'Breakout', 'Scalping'.
    - Use 'Manual' only if none of the above fit your reasoning.

    Risk management rules:
    - Minimum 2:1 reward-to-risk ratio (distance to TP >= 2x distance to SL)
    - Keep position size low (1 contract) unless high-probability setup (max 2-3)
    - POSITION LOCK: You are restricted to ONE active position/setup per instrument.
      If you already have a position or open order for a symbol, this tool will REJECT
      new orders for that symbol. You must evaluate and close/cancel the existing one first.

    Args:
        name: The name of the account holder
        symbol: The futures symbol — e.g. 'MNQ' or 'MGC'
        quantity: Number of contracts (keep low: 1 for normal, 2-3 for high probability)
        action: 'BUY' for long, 'SELL' for short
        entry_price: The limit/stop price for entry (ignored for MARKET)
        take_profit: Take-profit price level
        stop_loss: Stop-loss price level
        order_type: 'LIMIT', 'STOP', 'STOP_LIMIT', or 'MARKET'
        rationale: Your detailed reasoning for this trade
        timeframe_analysis: Summary of your multi-timeframe analysis (2m/5m/15m/1h confluence)
        strategy: The trading strategy used (e.g. 'Pivot Reversal', 'Breakout', etc.)
        allow_scaling: If True, allows adding to an existing position (up to 5 contracts max)
    """
    if order_type == "MARKET":
        return await execute_market_trade(
            name, symbol, quantity, action,
            take_profit, stop_loss, rationale, timeframe_analysis,
            strategy=strategy,
            allow_scaling=allow_scaling
        )
    return await execute_bracket_trade(
        name, symbol, quantity, action,
        entry_price, take_profit, stop_loss,
        order_type, rationale, timeframe_analysis,
        strategy=strategy,
        allow_scaling=allow_scaling
    )


@mcp.tool()
async def close_position(name: str, symbol: str, rationale: str) -> str:
    """Close any open position for the given symbol at market price immediately.
    Use this to 'flatten' a position if it no longer fits your strategy or if
    it is a 'naked' position (no stop-loss or take-profit orders).

    Args:
        name: The name of the account holder
        symbol: The futures symbol — e.g. 'MNQ' or 'MGC'
        rationale: Why you are closing the position
    """
    return await execute_close_position(name, symbol, rationale)


# ---------------------------------------------------------------------------
# Order management tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_open_orders() -> str:
    """Get all open/pending orders including parent and child orders (TP/SL).
    Use this to monitor your active bracket orders.
    """
    orders = await fetch_open_orders()
    return json.dumps(orders, indent=2)


@mcp.tool()
async def cancel_single_order(order_id: int) -> str:
    """Cancel a specific order. 
    You can provide either the session 'orderId' (short) or the IBKR 'permId' (long, as shown in TWS).
    Using 'permId' is HIGHLY RECOMMENDED as it remains valid across app restarts and logins.

    Args:
        order_id: The order ID or PermID to cancel
    """
    return await cancel_order(order_id)


@mcp.tool()
async def cancel_all_open_orders() -> str:
    """Cancel ALL open orders. Use this to flatten and start fresh.
    WARNING: This cancels all pending entries, take-profits, and stop-losses.
    """
    return await cancel_all_orders()


@mcp.tool()
async def modify_order(
    order_id: int,
    new_limit_price: float = None,
    new_stop_price: float = None,
) -> str:
    """Modify the prices of an existing open order. 
    You can provide either the session 'orderId' (short) or the IBKR 'permId' (long).
    Using 'permId' is RECOMMENDED for reliability.
    
    Args:
        order_id: The ID or PermID of the order to modify
        new_limit_price: New limit price (for LIMIT or STOP_LIMIT orders)
        new_stop_price: New stop price (for STOP or STOP_LIMIT orders)
    """
    return await modify_order_prices(order_id, new_limit_price, new_stop_price)


# ---------------------------------------------------------------------------
# Strategy tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def change_strategy(name: str, strategy: str) -> str:
    """Update your trading strategy notes for future reference.

    Args:
        name: The name of the account holder
        strategy: The new strategy description
    """
    return await change_account_strategy(name, strategy)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("portfolio://mcp_portfolio/{name}")
async def read_account_resource(name: str) -> str:
    return await get_account_report(name)


@mcp.resource("portfolio://strategy/{name}")
async def read_strategy_resource(name: str) -> str:
    return await get_account_strategy(name)


if __name__ == "__main__":
    mcp.run(transport='stdio')

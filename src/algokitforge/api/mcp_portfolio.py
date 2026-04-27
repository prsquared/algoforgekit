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
    fetch_open_orders,
    cancel_order,
    cancel_all_orders,
    get_account_report,
    change_account_strategy,
    get_account_strategy,
    ALLOWED_SYMBOLS,
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
    """Get the current real-time price of MNQ or MGC.

    Args:
        symbol: The futures symbol — must be 'MNQ' or 'MGC'
    """
    return await fetch_current_price(symbol)


@mcp.tool()
async def get_candles(symbol: str, bar_size: str, duration: str) -> str:
    """Fetch historical candlestick (OHLCV) data for MNQ or MGC.

    Args:
        symbol: The futures symbol — must be 'MNQ' or 'MGC'
        bar_size: Bar size — use '5 mins', '15 mins', or '1 hour'
        duration: Duration — use '1 D', '2 D', or '5 D'
    """
    candles = await fetch_candles(symbol, bar_size, duration)
    return json.dumps(candles, indent=2)


@mcp.tool()
async def get_full_technicals(symbol: str) -> str:
    """Get complete technical analysis data for a symbol: multi-timeframe candles
    (5-min, 15-min, 1-hour) plus RSI(14), Stochastic(14,3), EMA(9), EMA(21)
    computed on the 5-minute timeframe. Use this as your primary analysis tool
    before placing any trade.

    Args:
        symbol: The futures symbol — must be 'MNQ' or 'MGC'
    """
    data = await get_technicals_for_symbol(symbol)
    return json.dumps(data, indent=2)


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
) -> str:
    """Place a bracket order with entry + take-profit + stop-loss.
    ALWAYS use this tool for placing trades. Every trade MUST have a TP and SL.

    The entry order can be a LIMIT, STOP, STOP_LIMIT, or MARKET order.
    - Use LIMIT for entries at a better price (buy below / sell above market)
    - Use STOP for breakout entries (buy above / sell below market)
    - Use STOP_LIMIT for precise breakout entries with a price cap
    - Use MARKET only when you need immediate execution

    Risk management rules:
    - Minimum 2:1 reward-to-risk ratio (distance to TP >= 2x distance to SL)
    - Keep position size low (1 contract) unless high-probability setup (max 2-3)

    Args:
        name: The name of the account holder
        symbol: The futures symbol — must be 'MNQ' or 'MGC'
        quantity: Number of contracts (keep low: 1 for normal, 2-3 for high probability)
        action: 'BUY' for long, 'SELL' for short
        entry_price: The limit/stop price for entry (ignored for MARKET)
        take_profit: Take-profit price level
        stop_loss: Stop-loss price level
        order_type: 'LIMIT', 'STOP', 'STOP_LIMIT', or 'MARKET'
        rationale: Your detailed reasoning for this trade
        timeframe_analysis: Summary of your multi-timeframe analysis (5m/15m/1h confluence)
    """
    if order_type == "MARKET":
        return await execute_market_trade(
            name, symbol, quantity, action,
            take_profit, stop_loss, rationale, timeframe_analysis
        )
    return await execute_bracket_trade(
        name, symbol, quantity, action,
        entry_price, take_profit, stop_loss,
        order_type, rationale, timeframe_analysis
    )


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
    """Cancel a specific order by its order ID.

    Args:
        order_id: The order ID to cancel
    """
    return await cancel_order(order_id)


@mcp.tool()
async def cancel_all_open_orders() -> str:
    """Cancel ALL open orders. Use this to flatten and start fresh.
    WARNING: This cancels all pending entries, take-profits, and stop-losses.
    """
    return await cancel_all_orders()


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

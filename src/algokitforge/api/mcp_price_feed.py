import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from mcp.server.fastmcp import FastMCP
import asyncio
import math
from ib_async import Stock, IB

mcp = FastMCP("mcp_price_feed")
ib_instance = None

async def get_shared_ib() -> IB:
    global ib_instance
    if ib_instance is None or not ib_instance.isConnected():
        ib_instance = IB()
        client_id = int(os.getenv("IB_CLIENT_ID", "11"))
        await ib_instance.connectAsync('172.29.192.1', 7497, clientId=client_id, timeout=20)
    return ib_instance

@mcp.tool()
async def lookup_share_price(symbol: str) -> float:
    """This tool provides the current price of the given stock symbol.

    Args:
        symbol: the symbol of the stock
    """
    ib = await get_shared_ib()
    contract = Stock(symbol, 'SMART', 'USD')
    
    # Qualify contract
    contracts = await ib.qualifyContractsAsync(contract)
    if not contracts:
        return 0.0
        
    ticker = ib.reqMktData(contract, '', False, False)
    
    # Wait for price data to stream in
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

if __name__ == "__main__":
    mcp.run(transport='stdio')

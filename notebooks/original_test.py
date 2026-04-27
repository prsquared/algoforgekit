import asyncio
import logging
from ib_async import IB, Stock, LimitOrder, MarketOrder

# Uncomment to see debug logs
# import ib_async.util as util
# util.logToConsole(logging.DEBUG)

async def main():
    ib = IB()
    
    # 127.0.0.1 is the local machine where TWS / IB Gateway is running
    # 7497 is the default port for TWS Paper Trading. 
    # (Use 7496 for TWS Live Trading, 4001 for IB Gateway Live, 4002 for IB Gateway Paper)
    # clientId is an arbitrary number to identify your connection.
    print("Connecting to IBKR...")
    try:
        await ib.connectAsync('172.29.192.1', 7497, clientId=1, timeout=20)
        print("Successfully connected!")
    except ConnectionRefusedError:
        print("Connection refused. Make sure TWS/IB Gateway is running, logged in, and 'Enable ActiveX and Socket Clients' is checked in API Settings.")
        return
    except Exception as e:
        print(f"Connection error: {e}")
        return

    # 1. Define the contract (e.g., Apple stock)
    contract = Stock('AAPL', 'SMART', 'USD')
    
    # Qualify the contract to let IBKR fill in missing details (like the unique conId)
    print(f"Qualifying contract for {contract.symbol}...")
    contracts = await ib.qualifyContractsAsync(contract)
    if not contracts:
        print(f"Could not qualify contract for {contract.symbol}")
        return
    print(f"Contract qualified: {contract}")

    # 2. Get the current account details (optional)
    account_values = ib.accountValues()
    cash_balance = next((v.value for v in account_values if v.tag == 'TotalCashBalance' and v.currency == 'USD'), None)
    print(f"Account Cash Balance: {cash_balance} USD")

    # 3. Create an order
    # Here we create a Limit Order to buy 1 share at $10.00 (which is very low and unlikely to fill immediately)
    # To place a market order, you would use: order = MarketOrder('BUY', 1)
    action = 'BUY'
    quantity = 1
    limit_price = 10.00
    order = LimitOrder(action, quantity, limit_price)
    
    print(f"\nPlacing order: {action} {quantity} {contract.symbol} @ {limit_price} LMT")
    trade = ib.placeOrder(contract, order)
    
    # Define a callback to listen to order status updates
    def order_status_changed(trade):
        print(f" -> Order status changed: {trade.orderStatus.status} (Filled: {trade.orderStatus.filled}/{trade.orderStatus.totalQuantity})")
        
    trade.statusEvent += order_status_changed
    
    # Wait to see the initial status update (usually 'PendingSubmit' then 'Submitted')
    await asyncio.sleep(2)
    
    # 4. Cancel the order (for safety in this test script)
    print(f"\nCancelling the test order...")
    ib.cancelOrder(order)
    
    # Wait a bit for cancellation to go through
    await asyncio.sleep(2)
    
    print("Disconnecting...")
    ib.disconnect()

if __name__ == '__main__':
    # asyncio.run() creates a new event loop and runs the main coroutine
    asyncio.run(main())

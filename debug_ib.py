import asyncio
import random
from ib_async import IB

async def main():
    ib = IB()
    client_id = random.randint(3000, 9999)
    print(f"Connecting with clientId {client_id}...")
    await ib.connectAsync('172.29.192.1', 7497, clientId=client_id, timeout=20)
    print("Connected!")

    accounts = ib.managedAccounts()
    print(f"Managed accounts: {accounts}")

    # reqAccountSummary via raw client + read from wrapper
    print("\n=== reqAccountSummary ===")
    tags = "AccountType,NetLiquidation,TotalCashValue,SettledCash,AccruedCash,BuyingPower,AvailableFunds,ExcessLiquidity,GrossPositionValue"
    ib.client.reqAccountSummary(9001, "All", tags)
    await asyncio.sleep(5)
    
    # Read directly from wrapper
    print(f"wrapper.acctSummary has {len(ib.wrapper.acctSummary)} items")
    for key, val in ib.wrapper.acctSummary.items():
        print(f"  {key}: {val}")

    # reqPositions
    print("\n=== reqPositions ===")
    ib.client.reqPositions()
    await asyncio.sleep(3)
    
    print(f"wrapper.positions has {len(ib.wrapper.positions)} items")
    for key, val in ib.wrapper.positions.items():
        print(f"  {key}: {val}")

    # Also try accountSummaryAsync
    print("\n=== accountSummaryAsync ===")
    try:
        result = await asyncio.wait_for(ib.accountSummaryAsync(), timeout=10)
        print(f"Got {len(result)} items")
        for s in result:
            print(f"  {s.tag} = {s.value} ({s.currency})")
    except asyncio.TimeoutError:
        print("  Timed out after 10s")
    except Exception as e:
        print(f"  Error: {e}")

    ib.disconnect()

asyncio.run(main())

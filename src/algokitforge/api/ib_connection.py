import asyncio
from ib_async import IB

async def get_ib_connection(client_id: int, host='172.29.192.1', port=7497) -> IB:
    """Creates and returns an active connection to IBKR."""
    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=client_id, timeout=20)
        return ib
    except Exception as e:
        print(f"Failed to connect to IBKR on client {client_id}: {e}")
        raise e

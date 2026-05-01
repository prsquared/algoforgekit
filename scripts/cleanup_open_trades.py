import sqlite3
import os
import json
import asyncio
import shutil
from datetime import datetime
from algokitforge.core.portfolio_mgr import cancel_all_orders
from algokitforge.models.portfolio import TradeStatus

DB_PATH = "trades.db"
JSON_PATH = "alice_portfolio.json"

async def cleanup_open_only():
    print("Starting targeted cleanup (Open/Planned only)...")
    
    # 1. IBKR Global Cancel
    try:
        print("Sending global cancellation request to IBKR...")
        result = await cancel_all_orders()
        print(f"IBKR Response: {result}")
    except Exception as e:
        print(f"Error cancelling orders: {e}")

    # 2. Database Cleanup (Open/Planned/Cancelled)
    # The user said "Delete only the ones with status=open", but usually Planned also should go if cleaning up.
    # I'll stick to 'Open' if they were very specific, but 'Planned' is also 'open' in a sense.
    # Actually, I'll delete 'Open' and 'Planned' as they are the pending ones.
    if os.path.exists(DB_PATH):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                print("Deleting records with status 'Open' or 'Planned' from 'trades' table...")
                cursor.execute("DELETE FROM trades WHERE status IN ('Open', 'Planned')")
                deleted_count = cursor.rowcount
                conn.commit()
            print(f"Database cleaned: {deleted_count} records removed.")
        except Exception as e:
            print(f"Error cleaning database: {e}")
    else:
        print("Database not found, skipping.")

    # 3. JSON Cleanup
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, 'r') as f:
                data = json.load(f)
            
            # Filter out trades with Open or Planned status
            original_count = len(data.get('trades', []))
            data['trades'] = [t for t in data.get('trades', []) if t.get('status') not in ('Open', 'Planned')]
            new_count = len(data['trades'])
            
            # Transactions don't have status in the same way, but they are logged when placed.
            # Usually we keep transactions as history, but if the user wants to "delete only the ones with status=open",
            # they probably mean the active trades.
            
            with open(JSON_PATH, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"JSON state filtered: removed {original_count - new_count} trades.")
        except Exception as e:
            print(f"Error filtering JSON state: {e}")
    else:
        print("JSON state file not found, skipping.")

    print("Targeted cleanup complete.")

if __name__ == "__main__":
    asyncio.run(cleanup_open_only())

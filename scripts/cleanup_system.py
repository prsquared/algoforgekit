import sqlite3
import os
import json
import asyncio
import shutil
from datetime import datetime
from algokitforge.core.portfolio_mgr import cancel_all_orders

DB_PATH = "trades.db"
JSON_PATH = "alice_portfolio.json"

async def cleanup():
    print("Starting system cleanup...")
    
    # 1. IBKR Global Cancel
    try:
        print("Sending global cancellation request to IBKR...")
        result = await cancel_all_orders()
        print(f"IBKR Response: {result}")
    except Exception as e:
        print(f"Error cancelling orders: {e}")

    # 2. Database Cleanup
    if os.path.exists(DB_PATH):
        backup_db = f"{DB_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"Backing up database to {backup_db}...")
        shutil.copy2(DB_PATH, backup_db)
        
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                print("Deleting all records from 'trades' table...")
                cursor.execute("DELETE FROM trades")
                # Also reset autoincrement
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='trades'")
                conn.commit()
            print("Database cleaned successfully.")
        except Exception as e:
            print(f"Error cleaning database: {e}")
    else:
        print("Database not found, skipping.")

    # 3. JSON Cleanup
    if os.path.exists(JSON_PATH):
        backup_json = f"{JSON_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"Backing up JSON state to {backup_json}...")
        shutil.copy2(JSON_PATH, backup_json)
        
        try:
            with open(JSON_PATH, 'r') as f:
                data = json.load(f)
            
            print("Resetting transactions and trades in JSON state...")
            data['transactions'] = []
            data['trades'] = []
            
            with open(JSON_PATH, 'w') as f:
                json.dump(data, f, indent=2)
            print("JSON state reset successfully.")
        except Exception as e:
            print(f"Error cleaning JSON state: {e}")
    else:
        print("JSON state file not found, skipping.")

    print("Cleanup complete.")

if __name__ == "__main__":
    asyncio.run(cleanup())

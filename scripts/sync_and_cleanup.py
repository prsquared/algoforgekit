import sqlite3
import os
import json
import asyncio
import shutil
from datetime import datetime

DB_PATH = "trades.db"
JSON_PATH = "alice_portfolio.json"

def sync_and_cleanup():
    print("Syncing JSON with DB and performing targeted cleanup...")
    
    if not os.path.exists(DB_PATH) or not os.path.exists(JSON_PATH):
        print("Required files missing.")
        return

    # 1. Get current DB states
    db_trades = {}
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades")
        for row in cursor.fetchall():
            # Use a combination of symbol and timestamp as key if ID is not available or matching
            key = (row['symbol'], row['timestamp'])
            db_trades[key] = row['status']
    
    # 2. Update JSON with DB statuses and filter
    with open(JSON_PATH, 'r') as f:
        data = json.load(f)
    
    original_trades = data.get('trades', [])
    new_trades = []
    
    removed_count = 0
    updated_count = 0
    
    for t in original_trades:
        key = (t['symbol'], t['timestamp'])
        db_status = db_trades.get(key)
        
        if db_status:
            t['status'] = db_status
            updated_count += 1
        
        # Filter: Delete if status is 'Open' or 'Planned'
        if t.get('status') not in ('Open', 'Planned'):
            new_trades.append(t)
        else:
            removed_count += 1
            
    data['trades'] = new_trades
    
    with open(JSON_PATH, 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"Updated {updated_count} trade statuses from DB.")
    print(f"Removed {removed_count} trades with 'Open' or 'Planned' status from JSON.")
    print("Cleanup complete.")

if __name__ == "__main__":
    # First restore JSON from backup to get all records back before syncing
    # Find the most recent backup
    backups = [f for f in os.listdir('.') if f.startswith('alice_portfolio.json.backup_')]
    if backups:
        latest_backup = sorted(backups)[-1]
        print(f"Restoring from backup: {latest_backup}")
        shutil.copy2(latest_backup, JSON_PATH)
        sync_and_cleanup()
    else:
        print("No backup found to restore from.")

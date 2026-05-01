import sqlite3
import re

db_path = "trades.db"

STRATEGY_MAP = [
    (r"breakout", "Breakout"),
    (r"mean-reversion|mean reversion|pullback", "Mean Reversion"),
    (r"ema crossover|ema cross|ema alignment", "EMA Crossover"),
    (r"pivot reversal|reversal", "Pivot Reversal"),
    (r"pattern|triangle|h&s|head and shoulder", "Chart Pattern"),
    (r"continuation|trend following|trend", "Trend Following"),
    (r"scalp|scalping", "Scalping"),
]

def map_rationale_to_strategy(rationale):
    if not rationale:
        return "Manual"
    
    rat_lower = rationale.lower()
    for pattern, strategy in STRATEGY_MAP:
        if re.search(pattern, rat_lower):
            return strategy
    return "Manual"

def fix_strategies():
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, rationale, strategy FROM trades WHERE strategy = 'Manual'")
        rows = cursor.fetchall()
        
        updates = []
        for row in rows:
            new_strategy = map_rationale_to_strategy(row['rationale'])
            if new_strategy != "Manual":
                updates.append((new_strategy, row['id']))
                print(f"ID {row['id']}: Mapping Manual -> {new_strategy}")
        
        if updates:
            cursor.executemany("UPDATE trades SET strategy = ? WHERE id = ?", updates)
            conn.commit()
            print(f"Updated {len(updates)} trades.")
        else:
            print("No trades updated.")

if __name__ == "__main__":
    fix_strategies()

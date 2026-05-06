import sqlite3
import json
import os
from datetime import datetime
from typing import List, Optional
from algokitforge.models.portfolio import Trade, TradingStrategy, TradeStatus

# Unified database path for both bot and journal
DB_PATH = "/home/priyesh/projects/tradingjournal/trades.db"

class DatabaseMgr:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    strategy TEXT,
                    action TEXT,
                    quantity INTEGER,
                    planned_entry REAL,
                    planned_exit REAL,
                    planned_sl REAL,
                    fill_price REAL,
                    fill_time TEXT,
                    exit_price REAL,
                    end_time TEXT,
                    status TEXT,
                    rationale TEXT,
                    timestamp TEXT,
                    parent_order_id INTEGER,
                    tp_order_id INTEGER,
                    sl_order_id INTEGER,
                    perm_id INTEGER,
                    tp_perm_id INTEGER,
                    sl_perm_id INTEGER
                )
            """)
            conn.commit()
            
            # Migration to add new columns
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN commission REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN filled_quantity INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def add_trade(self, trade: Trade) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (
                    symbol, strategy, action, quantity, planned_entry, planned_exit, planned_sl,
                    status, rationale, timestamp, parent_order_id, tp_order_id, sl_order_id, 
                    perm_id, tp_perm_id, sl_perm_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.symbol, trade.strategy.value, trade.action, trade.quantity,
                trade.planned_entry, trade.planned_exit, trade.planned_sl,
                trade.status.value, trade.rationale, trade.timestamp,
                trade.parent_order_id, trade.tp_order_id, trade.sl_order_id, 
                trade.perm_id, trade.tp_perm_id, trade.sl_perm_id
            ))
            trade_id = cursor.lastrowid
            conn.commit()
            return trade_id

    def update_trade_fill(self, perm_id: int, fill_price: float, fill_time: str, order_id: Optional[int] = None, commission: float = 0.0):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            updated = False
            
            if perm_id and perm_id != 0:
                cursor.execute("""
                    UPDATE trades 
                    SET fill_price = ?, fill_time = ?, status = ?, commission = COALESCE(commission, 0.0) + ?
                    WHERE perm_id = ? AND status IN (?, ?, ?)
                """, (fill_price, fill_time, TradeStatus.FILLED.value, commission, perm_id, TradeStatus.OPEN.value, TradeStatus.PLANNED.value, TradeStatus.FILLED.value))
                if cursor.rowcount > 0:
                    updated = True
            
            if not updated and order_id:
                # Fallback to order_id if perm_id didn't match (e.g. if it was stored as 0)
                cursor.execute("""
                    UPDATE trades 
                    SET fill_price = ?, fill_time = ?, status = ?, perm_id = ?, commission = COALESCE(commission, 0.0) + ?
                    WHERE parent_order_id = ? AND status IN (?, ?, ?)
                """, (fill_price, fill_time, TradeStatus.FILLED.value, perm_id, commission, order_id, TradeStatus.OPEN.value, TradeStatus.PLANNED.value, TradeStatus.FILLED.value))
            conn.commit()

    def update_trade_close(self, perm_id: int, exit_price: float, end_time: str, order_id: Optional[int] = None, commission: float = 0.0):
        """Update trade when TP, SL or Manual close hits."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            updated = False
            
            # Match by parent perm_id (manual close) or child perm_id (TP/SL hit)
            if perm_id and perm_id != 0:
                cursor.execute("""
                    UPDATE trades 
                    SET exit_price = ?, end_time = ?, status = ?, commission = COALESCE(commission, 0.0) + ?
                    WHERE (perm_id = ? OR tp_perm_id = ? OR sl_perm_id = ?)
                """, (exit_price, end_time, TradeStatus.CLOSED.value, commission, perm_id, perm_id, perm_id))
                if cursor.rowcount > 0:
                    updated = True
            
            if not updated and order_id:
                # Fallback to order_id
                cursor.execute("""
                    UPDATE trades 
                    SET exit_price = ?, end_time = ?, status = ?, commission = COALESCE(commission, 0.0) + ?
                    WHERE (parent_order_id = ? OR tp_order_id = ? OR sl_order_id = ?)
                """, (exit_price, end_time, TradeStatus.CLOSED.value, commission, order_id, order_id, order_id))
            conn.commit()

    def get_trade_by_order_id(self, order_id: int) -> Optional[Trade]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE parent_order_id = ? OR tp_order_id = ? OR sl_order_id = ?", (order_id, order_id, order_id))
            row = cursor.fetchone()
            if row:
                return Trade(
                    id=row['id'],
                    symbol=row['symbol'],
                    strategy=TradingStrategy(row['strategy']),
                    action=row['action'],
                    quantity=row['quantity'],
                    planned_entry=row['planned_entry'],
                    planned_exit=row['planned_exit'],
                    planned_sl=row['planned_sl'],
                    fill_price=row['fill_price'],
                    fill_time=row['fill_time'],
                    exit_price=row['exit_price'],
                    end_time=row['end_time'],
                    status=TradeStatus(row['status']),
                    rationale=row['rationale'],
                    timestamp=row['timestamp'],
                    parent_order_id=row['parent_order_id'],
                    tp_order_id=row['tp_order_id'],
                    sl_order_id=row['sl_order_id'],
                    perm_id=row['perm_id'],
                    tp_perm_id=row['tp_perm_id'] if 'tp_perm_id' in row.keys() else None,
                    sl_perm_id=row['sl_perm_id'] if 'sl_perm_id' in row.keys() else None
                )
        return None

    def get_active_trade_by_symbol(self, symbol: str) -> Optional[Trade]:
        """Find the most recent active or recently closed-without-price trade for a symbol."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Order by ID DESC to get the most recent one
            cursor.execute("""
                SELECT * FROM trades 
                WHERE (symbol = ? OR ? LIKE '%' || symbol || '%') 
                AND (status IN (?, ?, ?) OR (status = ? AND (exit_price IS NULL OR exit_price = 0)))
                ORDER BY id DESC LIMIT 1
            """, (symbol, symbol, TradeStatus.OPEN.value, TradeStatus.FILLED.value, TradeStatus.PLANNED.value, TradeStatus.CLOSED.value))
            row = cursor.fetchone()
            if row:
                return Trade(
                    id=row['id'],
                    symbol=row['symbol'],
                    strategy=TradingStrategy(row['strategy']),
                    action=row['action'],
                    quantity=row['quantity'],
                    planned_entry=row['planned_entry'],
                    planned_exit=row['planned_exit'],
                    planned_sl=row['planned_sl'],
                    fill_price=row['fill_price'],
                    fill_time=row['fill_time'],
                    exit_price=row['exit_price'],
                    end_time=row['end_time'],
                    status=TradeStatus(row['status']),
                    rationale=row['rationale'],
                    timestamp=row['timestamp'],
                    parent_order_id=row['parent_order_id'],
                    tp_order_id=row['tp_order_id'],
                    sl_order_id=row['sl_order_id'],
                    perm_id=row['perm_id'],
                    tp_perm_id=row['tp_perm_id'] if 'tp_perm_id' in row.keys() else None,
                    sl_perm_id=row['sl_perm_id'] if 'sl_perm_id' in row.keys() else None
                )
        return None

    def cancel_trade(self, identifier: int):
        """Mark a trade as cancelled if its entry order is cancelled.
        Identifier can be a session order_id or a permanent perm_id.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # If identifier is large, it's likely a perm_id.
            # If it's small, it's a session order_id.
            # We use it to match either perm_id or parent_order_id.
            # To be safe, we only cancel the most recent matching OPEN/PLANNED trade if it's a session ID.
            if identifier > 100000: # Heuristic for perm_id
                # ONLY cancel if it's the parent perm_id.
                # Cancelling a child leg (TP/SL) should NOT cancel the parent trade.
                cursor.execute("""
                    UPDATE trades 
                    SET status = ?
                    WHERE perm_id = ?
                    AND status IN (?, ?)
                """, (TradeStatus.CANCELLED.value, identifier, TradeStatus.OPEN.value, TradeStatus.PLANNED.value))
            else:
                # ONLY cancel if it's the parent_order_id.
                cursor.execute("""
                    UPDATE trades 
                    SET status = ?
                    WHERE id = (
                        SELECT id FROM trades 
                        WHERE parent_order_id = ?
                        AND status IN (?, ?)
                        ORDER BY id DESC LIMIT 1
                    )
                """, (TradeStatus.CANCELLED.value, identifier, TradeStatus.OPEN.value, TradeStatus.PLANNED.value))
            conn.commit()

    def update_trade_status(self, identifier: int, status: TradeStatus):
        """Generic status update by any associated order ID or perm ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if identifier > 100000:
                cursor.execute("""
                    UPDATE trades 
                    SET status = ?
                    WHERE (perm_id = ? OR tp_perm_id = ? OR sl_perm_id = ?)
                """, (status.value, identifier, identifier, identifier))
            else:
                cursor.execute("""
                    UPDATE trades 
                    SET status = ?
                    WHERE id = (
                        SELECT id FROM trades 
                        WHERE (parent_order_id = ? OR tp_order_id = ? OR sl_order_id = ?)
                        ORDER BY id DESC LIMIT 1
                    )
                """, (status.value, identifier, identifier, identifier))
            conn.commit()

            conn.commit()

    def sync_perm_id(self, order_id: int, perm_id: int):
        """Update the perm_id of a trade if it was initially missing (0)."""
        if not order_id or not perm_id:
            return
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trades 
                SET perm_id = ?
                WHERE parent_order_id = ? AND (perm_id IS NULL OR perm_id = 0)
            """, (perm_id, order_id))
            
            cursor.execute("""
                UPDATE trades 
                SET tp_perm_id = ?
                WHERE tp_order_id = ? AND (tp_perm_id IS NULL OR tp_perm_id = 0)
            """, (perm_id, order_id))
            
            cursor.execute("""
                UPDATE trades 
                SET sl_perm_id = ?
                WHERE sl_order_id = ? AND (sl_perm_id IS NULL OR sl_perm_id = 0)
            """, (perm_id, order_id))
            conn.commit()

db_mgr = DatabaseMgr()

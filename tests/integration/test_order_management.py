import pytest
import sqlite3
import os
import tempfile
import asyncio
from datetime import datetime

# Patch db_path before importing modules
from algokitforge.core.database import db_mgr, DatabaseMgr
from algokitforge.models.portfolio import Trade, TradingStrategy, TradeStatus
from algokitforge.core.portfolio_mgr import on_trade_filled, on_order_status

# --- Mocks ---
class MockExecution:
    def __init__(self, side, shares, avgPrice, time, permId, orderId):
        self.side = side
        self.shares = shares
        self.avgPrice = avgPrice
        self.time = time
        self.permId = permId
        self.orderId = orderId

class MockCommissionReport:
    def __init__(self, commission):
        self.commission = commission

class MockContract:
    def __init__(self, symbol):
        self.symbol = symbol
        self.localSymbol = symbol

class MockFill:
    def __init__(self, execution, commissionReport, contract):
        self.execution = execution
        self.commissionReport = commissionReport
        self.contract = contract

class MockOrder:
    def __init__(self, orderId, permId, action="BUY"):
        self.orderId = orderId
        self.permId = permId
        self.action = action

class MockOrderStatus:
    def __init__(self, status):
        self.status = status

class MockTradeEvent:
    def __init__(self, order, orderStatus, contract=None):
        self.order = order
        self.orderStatus = orderStatus
        self.contract = contract or MockContract("MOCK")

@pytest.fixture(autouse=True)
def setup_test_db():
    # Create temp DB file
    fd, temp_path = tempfile.mkstemp()
    os.close(fd)
    
    # Patch global db_mgr
    db_mgr.db_path = temp_path
    db_mgr._init_db()
    
    yield
    
    # Teardown
    os.remove(temp_path)

def create_trade(symbol="MOCK", action="BUY", status=TradeStatus.PLANNED, 
                 parent_id=100, tp_id=101, sl_id=102, 
                 parent_perm=1000, tp_perm=1001, sl_perm=1002):
    return Trade(
        id=0,
        symbol=symbol,
        strategy=TradingStrategy.MANUAL,
        action=action,
        quantity=10,
        planned_entry=150.0,
        planned_exit=160.0,
        planned_sl=140.0,
        fill_price=0.0,
        exit_price=0.0,
        status=status,
        rationale="Test",
        timestamp=datetime.now().isoformat(),
        parent_order_id=parent_id,
        tp_order_id=tp_id,
        sl_order_id=sl_id,
        perm_id=parent_perm,
        tp_perm_id=tp_perm,
        sl_perm_id=sl_perm
    )

@pytest.mark.asyncio
async def test_trade_entry_and_partial_fills():
    # 1. Setup DB with a PLANNED trade
    trade = create_trade(status=TradeStatus.PLANNED)
    db_mgr.add_trade(trade)
    
    # 2. First partial fill chunk (5 shares @ 151.0)
    exec1 = MockExecution("BUY", 5, 151.0, datetime.now(), 1000, 100)
    comm1 = MockCommissionReport(1.25)
    fill1 = MockFill(exec1, comm1, MockContract("MOCK"))
    
    await on_trade_filled(MockTradeEvent(None, None, MockContract("MOCK")), fill1)
    
    # Verify DB state
    db_trade = db_mgr.get_trade_by_order_id(100)
    assert db_trade.status == TradeStatus.FILLED
    assert db_trade.fill_price == 151.0
    
    with sqlite3.connect(db_mgr.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT commission FROM trades WHERE parent_order_id=100")
        assert cursor.fetchone()['commission'] == 1.25
        
    # 3. Second partial fill chunk (5 shares @ 152.0)
    exec2 = MockExecution("BUY", 5, 152.0, datetime.now(), 1000, 100)
    comm2 = MockCommissionReport(1.25)
    fill2 = MockFill(exec2, comm2, MockContract("MOCK"))
    
    await on_trade_filled(MockTradeEvent(None, None, MockContract("MOCK")), fill2)
    
    # Verify DB state
    db_trade = db_mgr.get_trade_by_order_id(100)
    assert db_trade.status == TradeStatus.FILLED
    assert db_trade.fill_price == 152.0 # Updated to last chunk price
    
    with sqlite3.connect(db_mgr.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT commission FROM trades WHERE parent_order_id=100")
        assert cursor.fetchone()['commission'] == 2.50 # Accumulated correctly without deadlock

@pytest.mark.asyncio
async def test_take_profit_and_stop_loss_hits():
    # 1. Setup DB with a FILLED trade
    trade = create_trade(status=TradeStatus.FILLED)
    trade.fill_price = 150.0
    db_mgr.add_trade(trade)
    
    # 2. TP Hit (SELL 10 @ 160.0)
    exec_tp = MockExecution("SELL", 10, 160.0, datetime.now(), 1001, 101) # tp_perm_id = 1001
    comm = MockCommissionReport(2.0)
    fill = MockFill(exec_tp, comm, MockContract("MOCK"))
    
    await on_trade_filled(MockTradeEvent(None, None, MockContract("MOCK")), fill)
    
    # Verify DB state
    db_trade = db_mgr.get_trade_by_order_id(100)
    assert db_trade.status == TradeStatus.CLOSED
    assert db_trade.exit_price == 160.0
    
    with sqlite3.connect(db_mgr.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT commission FROM trades WHERE parent_order_id=100")
        assert cursor.fetchone()['commission'] == 2.0

@pytest.mark.asyncio
async def test_cancellations():
    # 1. Setup DB with an OPEN trade
    trade = create_trade(status=TradeStatus.OPEN)
    db_mgr.add_trade(trade)
    
    # 2. Cancel the child Stop Loss order
    # This should NOT cancel the parent trade.
    child_event = MockTradeEvent(MockOrder(102, 1002), MockOrderStatus("Cancelled"))
    await on_order_status(child_event)
    
    db_trade = db_mgr.get_trade_by_order_id(100)
    assert db_trade.status == TradeStatus.OPEN # Remains open
    
    # 3. Cancel the parent entry order
    parent_event = MockTradeEvent(MockOrder(100, 1000), MockOrderStatus("Cancelled"))
    await on_order_status(parent_event)
    
    db_trade = db_mgr.get_trade_by_order_id(100)
    assert db_trade.status == TradeStatus.CANCELLED # Now it's cancelled

@pytest.mark.asyncio
async def test_manual_closures():
    # 1. Setup DB with a FILLED active trade
    trade = create_trade(status=TradeStatus.FILLED)
    db_mgr.add_trade(trade)
    
    # 2. Simulate manual TWS close. This order has no permId matching our child legs.
    exec_manual = MockExecution("SELL", 10, 155.0, datetime.now(), 9999, 8888) 
    comm = MockCommissionReport(1.5)
    fill = MockFill(exec_manual, comm, MockContract("MOCK"))
    
    await on_trade_filled(MockTradeEvent(None, None, MockContract("MOCK")), fill)
    
    # Verify DB state
    db_trade = db_mgr.get_trade_by_order_id(100)
    assert db_trade.status == TradeStatus.CLOSED
    assert db_trade.exit_price == 155.0

@pytest.mark.asyncio
async def test_sync_perm_id_fallback():
    # 1. Setup DB with trade that has permId=0 (timeout fallback)
    trade = create_trade(status=TradeStatus.OPEN, parent_perm=0, tp_perm=0, sl_perm=0)
    db_mgr.add_trade(trade)
    
    # 2. Broker eventually sends on_order_status with the permIds
    await on_order_status(MockTradeEvent(MockOrder(100, 5000), MockOrderStatus("Submitted")))
    await on_order_status(MockTradeEvent(MockOrder(101, 5001), MockOrderStatus("Submitted")))
    await on_order_status(MockTradeEvent(MockOrder(102, 5002), MockOrderStatus("Submitted")))
    
    # Verify they were patched into the DB
    db_trade = db_mgr.get_trade_by_order_id(100)
    assert db_trade.perm_id == 5000
    assert db_trade.tp_perm_id == 5001
    assert db_trade.sl_perm_id == 5002
    
    # 3. Simulate fill using the new permId
    exec_fill = MockExecution("BUY", 10, 150.0, datetime.now(), 5000, 100)
    fill = MockFill(exec_fill, MockCommissionReport(1.0), MockContract("MOCK"))
    await on_trade_filled(MockTradeEvent(None, None, MockContract("MOCK")), fill)
    
    db_trade = db_mgr.get_trade_by_order_id(100)
    assert db_trade.status == TradeStatus.FILLED

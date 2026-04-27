import pytest
from algokitforge.models.portfolio import Transaction, AccountState

def test_transaction_defaults():
    t = Transaction(
        symbol="MNQ",
        quantity=1,
        price=20000.5,
        timestamp="2023-01-01T10:00:00",
        rationale="Test trade",
        action="BUY"
    )
    assert t.order_type == "MARKET"
    assert t.stop_loss is None
    assert t.take_profit is None
    assert t.timeframe_analysis is None

def test_transaction_fields():
    t = Transaction(
        symbol="MGC",
        quantity=2,
        price=2500.0,
        timestamp="2023-01-01T11:00:00",
        rationale="Gold trade",
        action="SELL",
        order_type="LIMIT",
        stop_loss=2600.0,
        take_profit=2400.0,
        timeframe_analysis="5m overbought, 15m bear flag"
    )
    assert t.order_type == "LIMIT"
    assert t.stop_loss == 2600.0
    assert t.take_profit == 2400.0
    assert "bear flag" in t.timeframe_analysis

def test_account_state_defaults():
    a = AccountState(name="TestAccount")
    assert a.name == "TestAccount"
    assert a.strategy == ""
    assert a.transactions == []

def test_account_state_with_data():
    t = Transaction(
        symbol="MNQ",
        quantity=1,
        price=20000.0,
        timestamp="2023-01-01T10:00:00",
        rationale="Test",
        action="BUY"
    )
    a = AccountState(name="TestAccount", strategy="SCALP", transactions=[t])
    assert a.strategy == "SCALP"
    assert len(a.transactions) == 1
    assert a.transactions[0].symbol == "MNQ"

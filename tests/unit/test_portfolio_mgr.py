import pytest
import os
import json
from unittest.mock import patch, mock_open

from algokitforge.core.portfolio_mgr import (
    _make_contract,
    compute_rsi,
    compute_stochastic,
    compute_ema,
    load_account_state,
    save_account_state,
    ALLOWED_SYMBOLS,
)
from algokitforge.models.portfolio import AccountState


def test_make_contract_valid():
    for symbol in ALLOWED_SYMBOLS:
        contract = _make_contract(symbol)
        assert contract.symbol == symbol
        if symbol == "MNQ":
            assert contract.exchange == "CME"
            assert contract.currency == "USD"
        elif symbol == "MGC":
            assert contract.exchange == "COMEX"
            assert contract.currency == "USD"

def test_make_contract_invalid():
    with pytest.raises(ValueError, match="Only.*are allowed"):
        _make_contract("INVALID")

def test_compute_ema():
    closes = [10, 11, 12, 13, 14, 15]
    period = 3
    ema = compute_ema(closes, period)
    assert len(ema) == len(closes)
    # The first (period-1) should be None
    assert ema[0] is None
    assert ema[1] is None
    # 3rd element is SMA
    assert ema[2] == sum([10, 11, 12]) / 3
    # 4th element is EMA
    multiplier = 2 / (period + 1)
    expected_4th = (13 - ema[2]) * multiplier + ema[2]
    assert ema[3] == round(expected_4th, 4)

def test_compute_ema_short_list():
    closes = [10, 11]
    ema = compute_ema(closes, 3)
    assert ema == [None, None]

def test_compute_rsi_flat():
    closes = [100] * 20
    rsi = compute_rsi(closes, 14)
    assert len(rsi) == 20
    assert rsi[:14] == [None] * 14
    # With no loss, RSI is 100
    assert rsi[14] == 100.0

def test_compute_rsi_gaining():
    closes = list(range(100, 120))
    rsi = compute_rsi(closes, 14)
    # With no loss, RSI is 100
    assert rsi[14] == 100.0

def test_compute_rsi_losing():
    closes = list(range(120, 100, -1))
    rsi = compute_rsi(closes, 14)
    # With no gain, RSI should be 0.0, calculated as 100 - (100/(1+0))
    assert rsi[14] == 0.0

def test_compute_stochastic():
    highs = [15, 16, 17, 18, 19, 20]
    lows =  [10, 11, 12, 13, 14, 15]
    closes = [12, 13, 14, 15, 16, 17]
    
    # K period 3, D period 2
    stoch = compute_stochastic(highs, lows, closes, k_period=3, d_period=2)
    
    k_vals = stoch["percent_k"]
    d_vals = stoch["percent_d"]
    
    assert len(k_vals) == 6
    assert len(d_vals) == 6
    
    # First 2 should be None for K
    assert k_vals[0] is None
    assert k_vals[1] is None
    
    # 3rd element K val
    # window highs: 15, 16, 17 -> max 17
    # window lows: 10, 11, 12 -> min 10
    # close: 14
    # k_val = (14 - 10) / (17 - 10) * 100 = 4 / 7 * 100 = 57.14
    assert k_vals[2] == 57.14
    
    # 3rd element D val: D period is 2, so need 2 valid K vals. Only 1 so far.
    assert d_vals[2] is None
    
    # 4th element K val
    # window highs: 16, 17, 18 -> max 18
    # window lows: 11, 12, 13 -> min 11
    # close: 15
    # k_val = (15 - 11) / (18 - 11) * 100 = 4 / 7 * 100 = 57.14
    assert k_vals[3] == 57.14
    
    # 4th element D val: average of 57.14 and 57.14 = 57.14
    assert d_vals[3] == 57.14

def test_load_account_state_new():
    with patch("os.path.exists", return_value=False):
        state = load_account_state("TestAcct")
        assert state.name == "TestAcct"

def test_load_account_state_existing():
    mock_data = {
        "name": "TestAcct",
        "strategy": "MOMENTUM",
        "transactions": []
    }
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=json.dumps(mock_data))):
            state = load_account_state("TestAcct")
            assert state.name == "TestAcct"
            assert state.strategy == "MOMENTUM"

def test_save_account_state():
    state = AccountState(name="TestAcct", strategy="SCALPING")
    mock_file = mock_open()
    with patch("builtins.open", mock_file):
        save_account_state(state)
        mock_file.assert_called_once_with("testacct_portfolio.json", 'w')
        # Check that written content is valid json and contains the strategy
        written = "".join(call.args[0] for call in mock_file().write.call_args_list)
        parsed = json.loads(written)
        assert parsed["name"] == "TestAcct"
        assert parsed["strategy"] == "SCALPING"

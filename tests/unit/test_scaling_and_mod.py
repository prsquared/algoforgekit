import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from algokitforge.core.portfolio_mgr import check_existing_position, modify_order_prices

@pytest.mark.asyncio
async def test_check_existing_position_scaling_allowed():
    """Test that scaling is allowed when allow_scaling=True and qty < 5."""
    mock_holdings = {
        "MNQM4": {"quantity": 2, "avg_cost": 18000, "mkt_price": 18100, "unrealized_pnl": 200}
    }
    
    with patch("algokitforge.core.portfolio_mgr.fetch_holdings", AsyncMock(return_value=mock_holdings)):
        with patch("algokitforge.core.portfolio_mgr.fetch_open_orders", AsyncMock(return_value=[])):
            # With allow_scaling=False, it should reject
            err = await check_existing_position("MNQ", allow_scaling=False)
            assert "Existing position found" in err
            
            # With allow_scaling=True, it should allow (return None)
            err = await check_existing_position("MNQ", allow_scaling=True)
            assert err is None

@pytest.mark.asyncio
async def test_check_existing_position_scaling_limit():
    """Test that scaling is rejected when qty >= 5."""
    mock_holdings = {
        "MNQM4": {"quantity": 5, "avg_cost": 18000, "mkt_price": 18100, "unrealized_pnl": 500}
    }
    
    with patch("algokitforge.core.portfolio_mgr.fetch_holdings", AsyncMock(return_value=mock_holdings)):
        with patch("algokitforge.core.portfolio_mgr.fetch_open_orders", AsyncMock(return_value=[])):
            err = await check_existing_position("MNQ", allow_scaling=True)
            assert "already at max safety limit" in err

@pytest.mark.asyncio
async def test_modify_order_prices_success():
    """Test successful order modification."""
    mock_ib = MagicMock()
    mock_trade = MagicMock()
    mock_trade.order.orderId = 12345
    mock_trade.order.lmtPrice = 18000
    mock_trade.order.auxPrice = 17500
    mock_trade.contract = MagicMock()
    
    mock_ib.openTrades.return_value = [mock_trade]
    
    with patch("algokitforge.core.portfolio_mgr.get_ib", AsyncMock(return_value=mock_ib)):
        # Modify limit price
        result = await modify_order_prices(12345, lmt_price=18100)
        assert "modification sent" in result
        assert "lmtPrice -> 18100" in result
        assert mock_trade.order.lmtPrice == 18100
        mock_ib.placeOrder.assert_called_once()

@pytest.mark.asyncio
async def test_modify_order_prices_not_found():
    """Test modification when order ID doesn't exist."""
    mock_ib = MagicMock()
    mock_ib.openTrades.return_value = []
    
    with patch("algokitforge.core.portfolio_mgr.get_ib", AsyncMock(return_value=mock_ib)):
        result = await modify_order_prices(999, lmt_price=18100)
        assert "not found" in result

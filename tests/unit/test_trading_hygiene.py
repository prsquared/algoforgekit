import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from algokitforge.core.portfolio_mgr import cancel_order, execute_close_position, on_trade_filled

@pytest.mark.asyncio
async def test_cancel_order_already_done():
    """Test that cancel_order rejects cancelling a completed trade."""
    mock_ib = MagicMock()
    mock_trade = MagicMock()
    mock_trade.order.orderId = 13
    mock_trade.isDone.return_value = True
    mock_trade.orderStatus.status = "Filled"
    
    mock_ib.openTrades.return_value = [mock_trade]
    
    with patch("algokitforge.core.portfolio_mgr.get_ib", AsyncMock(return_value=mock_ib)):
        result = await cancel_order(13)
        assert "already 'Filled'" in result
        mock_ib.cancelOrder.assert_not_called()

@pytest.mark.asyncio
async def test_cancel_order_sends_notification():
    """Test that cancel_order sends a notification on success."""
    mock_ib = MagicMock()
    mock_trade = MagicMock()
    mock_trade.order.orderId = 13
    mock_trade.isDone.return_value = False
    mock_trade.contract.localSymbol = "MNQM4"
    
    mock_ib.openTrades.return_value = [mock_trade]
    
    with patch("algokitforge.core.portfolio_mgr.get_ib", AsyncMock(return_value=mock_ib)):
        with patch("algokitforge.core.portfolio_mgr.pushover_mgr.send_notification", AsyncMock()) as mock_notify:
            result = await cancel_order(13)
            assert "Cancel request sent" in result
            mock_ib.cancelOrder.assert_called_once_with(mock_trade.order)
            
            # Wait a bit for the async task to run
            await asyncio.sleep(0.1)
            mock_notify.assert_called_once()
            assert "CANCELLED Order 13" in mock_notify.call_args[0][0]

@pytest.mark.asyncio
async def test_execute_close_position_hygiene():
    """Test that execute_close_position cancels open orders correctly."""
    mock_ib = MagicMock()
    
    # Mock positions
    mock_pos = MagicMock()
    mock_pos.contract.localSymbol = "MNQM4"
    mock_pos.position = 1
    mock_ib.positions.return_value = [mock_pos]
    
    # Mock open trades
    mock_trade = MagicMock()
    mock_trade.contract.localSymbol = "MNQM4"
    mock_trade.isDone.return_value = False
    mock_ib.openTrades.return_value = [mock_trade]
    
    # Mock market data / qualify contract
    with patch("algokitforge.core.portfolio_mgr.get_ib", AsyncMock(return_value=mock_ib)), \
         patch("algokitforge.core.portfolio_mgr.fetch_holdings", AsyncMock(return_value={"MNQM4": {"quantity": 1}})), \
         patch("algokitforge.core.portfolio_mgr.pushover_mgr.send_notification", AsyncMock()):
            
            # We also need to mock placeOrder and the wait loop
            mock_ib.placeOrder.return_value = MagicMock()
            
            result = await execute_close_position("Alice", "MNQ", "Test")
            
            # Check that existing orders were cancelled
            mock_ib.cancelOrder.assert_called_with(mock_trade.order)
            # Check that a market order was placed to close
            mock_ib.placeOrder.assert_called()

@pytest.mark.asyncio
async def test_on_trade_filled_notification():
    """Test the asynchronous fill notification logic."""
    mock_trade = MagicMock()
    mock_trade.contract.localSymbol = "MNQM4"
    mock_trade.order.orderType = "STP"
    mock_trade.order.parentId = 100
    
    mock_fill = MagicMock()
    mock_fill.execution.side = "SELL"
    mock_fill.execution.shares = 1
    mock_fill.execution.avgPrice = 18000.50
    
    with patch("algokitforge.core.portfolio_mgr.pushover_mgr.send_notification", AsyncMock()) as mock_notify:
        await on_trade_filled(mock_trade, mock_fill)
        
        mock_notify.assert_called_once()
        msg = mock_notify.call_args[0][0]
        assert "STOP LOSS HIT" in msg
        assert "MNQM4" in msg
        assert "18000.5" in msg

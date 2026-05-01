import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from algokitforge.core.algo_trader import get_model, Trader
from agents import OpenAIChatCompletionsModel

def test_get_model_default():
    model = get_model("gpt-5-mini")
    assert isinstance(model, OpenAIChatCompletionsModel)
    assert model.model == "gpt-5-mini"

@patch("algokitforge.core.algo_trader.deepseek_client", new="mock_client")
def test_get_model_deepseek():
    model = get_model("deepseek-chat")
    assert isinstance(model, OpenAIChatCompletionsModel)
    assert model.model == "deepseek-chat"

@patch("algokitforge.core.algo_trader.gemini_client", new="mock_client")
def test_get_model_gemini():
    model = get_model("gemini-1.5-pro")
    assert isinstance(model, OpenAIChatCompletionsModel)
    assert model.model == "gemini-1.5-pro"

def test_trader_init():
    trader = Trader(name="Alice", model_name="gpt-5-mini")
    assert trader.name == "Alice"
    assert trader.model_name == "gpt-5-mini"
    assert trader.agent is None

@pytest.mark.asyncio
async def test_trader_create_agent():
    trader = Trader(name="Alice", model_name="gpt-5-mini")
    agent = await trader.create_agent([])
    assert agent is not None
    assert agent.name == "Alice"
    assert agent.model.model == "gpt-5-mini"

@pytest.mark.asyncio
@patch("algokitforge.core.algo_trader.Trader.get_strategy", new_callable=AsyncMock)
@patch("algokitforge.core.algo_trader.Runner.run", new_callable=AsyncMock)
async def test_trader_run_agent(mock_runner_run, mock_get_strategy):
    mock_get_strategy.return_value = "Test Strategy"
    
    trader = Trader(name="Alice")
    await trader.run_agent([])
    
    # Verify strategy was fetched
    mock_get_strategy.assert_called_once()
    
    # Verify runner was called
    mock_runner_run.assert_called_once()
    args, kwargs = mock_runner_run.call_args
    assert args[0] == trader.agent
    assert "Test Strategy" in args[1] # Check if message string has strategy
    assert kwargs.get("max_turns") == 30

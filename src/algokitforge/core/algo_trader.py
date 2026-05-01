from contextlib import AsyncExitStack
import json
import os
import asyncio

from agents import Agent, Runner, OpenAIChatCompletionsModel
from agents.mcp import MCPServerStdio
from algokitforge.core.prompts import trader_instructions, trade_message
from algokitforge.core.mcp_config import trader_mcp_server_params
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(override=True)
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
google_api_key = os.getenv("GOOGLE_API_KEY")

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

deepseek_client = AsyncOpenAI(base_url=DEEPSEEK_BASE_URL, api_key=deepseek_api_key) if deepseek_api_key else None
gemini_client = AsyncOpenAI(base_url=GEMINI_BASE_URL, api_key=google_api_key) if google_api_key else None
openai_client = AsyncOpenAI() # default

def get_model(model_name: str):
    if "deepseek" in model_name and deepseek_client:
        return OpenAIChatCompletionsModel(model=model_name, openai_client=deepseek_client)
    elif "gemini" in model_name and gemini_client:
        return OpenAIChatCompletionsModel(model=model_name, openai_client=gemini_client)
    else:
        # Fallback to default OpenAI
        return OpenAIChatCompletionsModel(model=model_name, openai_client=openai_client)

class Trader:
    def __init__(self, name: str, model_name="gpt-5-mini"):
        self.name = name
        self.agent = None
        self.model_name = model_name

    async def create_agent(self, trader_mcp_servers) -> Agent:
        self.agent = Agent(
            name=self.name,
            instructions=trader_instructions(self.name),
            model=get_model(self.model_name),
            tools=[],
            mcp_servers=trader_mcp_servers,
        )
        return self.agent

    async def get_strategy(self) -> str:
        """Fetch strategy from local JSON file — no IB connection needed."""
        from algokitforge.core.portfolio_mgr import get_account_strategy
        return await get_account_strategy(self.name)

    async def run_agent(self, trader_mcp_servers):
        self.agent = await self.create_agent(trader_mcp_servers)
        strategy = await self.get_strategy()
        
        # Day trading always evaluates the market
        message = trade_message(self.name, strategy, "Use your get_balance, get_holdings, and get_open_orders tools to check your current account state.")
        
        await Runner.run(self.agent, message, max_turns=30)

    async def run(self):
        try:
            async with AsyncExitStack() as stack:
                trader_mcp_servers = [
                    await stack.enter_async_context(
                        MCPServerStdio(params, client_session_timeout_seconds=120)
                    )
                    for params in trader_mcp_server_params
                ]
                await self.run_agent(trader_mcp_servers)
        except Exception as e:
            print(f"Error running trader {self.name}: {e}")

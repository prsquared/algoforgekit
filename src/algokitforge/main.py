import asyncio
import os
import sys

# Ensure the parent `src` directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from algokitforge.core.algo_trader import Trader
from algokitforge.core.portfolio_mgr import is_market_session_active

# Using default models
model_name = os.getenv("DEFAULT_MODEL", "gpt-5-mini") # Upgraded default model for day trading

def create_trader() -> Trader:
    # Creating a single trader since IBKR paper account typically handles one login well
    return Trader("Alice", model_name=model_name)

async def main():
    print("Starting the Day Trading Floor...")
    
    # Start persistent fill listener for trade updates and notifications
    from algokitforge.core.portfolio_mgr import start_fill_listener
    try:
        await start_fill_listener()
    except Exception as e:
        print(f"Warning: Could not start persistent fill listener: {e}")
        
    trader = create_trader()
    
    # Run the trader loop periodically
    while True:
        if not is_market_session_active():
            sessions = os.getenv("MARKET_SESSION", "None")
            print(f"Outside enabled market sessions ({sessions}). Skipping analysis round...")
            await asyncio.sleep(60)
            continue

        print("Starting a market analysis round...")
        await trader.run()
        print("Market analysis round finished. Waiting 1 minute for next candle...")
        await asyncio.sleep(60)  # Faster cycle for day trading (every 2 mins)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Shutting down] Day Trading Floor closed gracefully.")
        sys.exit(0)

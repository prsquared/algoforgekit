import asyncio
import os
import sys

# Ensure the parent `src` directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from algokitforge.core.algo_trader import Trader

# Using default models
model_name = os.getenv("DEFAULT_MODEL", "gpt-4o") # Upgraded default model for day trading

def create_trader() -> Trader:
    # Creating a single trader since IBKR paper account typically handles one login well
    return Trader("Alice", model_name=model_name)

async def main():
    print("Starting the Day Trading Floor...")
    trader = create_trader()
    
    # Run the trader loop periodically
    while True:
        print("Starting a market analysis round...")
        await trader.run()
        print("Market analysis round finished. Waiting 2 minutes for next candle...")
        await asyncio.sleep(120)  # Faster cycle for day trading (every 2 mins)

if __name__ == "__main__":
    asyncio.run(main())

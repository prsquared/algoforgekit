import os

base_env = os.environ.copy()
base_env["PYTHONPATH"] = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

# Single MCP server handles all IB operations (portfolio + market data) with one connection
trader_mcp_server_params = [
    {"command": "uv", "args": ["run", "src/algokitforge/api/mcp_portfolio.py"], "env": base_env},
]

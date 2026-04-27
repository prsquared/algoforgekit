# AlgoKitForge ⚒️

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AlgoKitForge** AI-powered algorithmic trading system architected for Interactive Brokers (IBKR). It combines the strategic reasoning of Large Language Models (LLMs) with high-performance execution to sim trade Micro-Futures (MNQ, MGC) with precision.

> [!IMPORTANT]
> **Educational Purposes Only**: This project is for simulation and educational research only. It is not intended for live trading. Trading futures involves significant risk, and you should never trade with capital you cannot afford to lose.

## 🚀 Key Features

*   **Agentic Intelligence**: Powered by `OpenAI AgentSDK`, utilizing specialized AI agents to interpret market sentiment and technical setups.
*   **Multi-Timeframe Analysis (MTF)**: Synchronized analysis across 5m, 15m, and 1h intervals to filter high-probability entries.
*   **Deep Technical Indicators**: Built-in support for RSI, Stochastic oscillators, and trend-following metrics.
*   **Robust IBKR Integration**: Leverages `ib-async` for asynchronous, non-blocking communication with TWS or IB Gateway.
*   **Systematic Risk Management**:
    *   Automated 2:1 Risk-to-Reward (R:R) ratio targeting.
    *   Hard-coded Stop-Loss (SL) and Take-Profit (TP) orders sent on entry.
    *   Dynamic position sizing based on account equity and trade probability.
*   **Modern Infrastructure**: Managed with `uv` for lightning-fast dependency resolution and deterministic environments.

## 🏗️ Project Structure

```text
algokitforge/
├── src/
│   └── algokitforge/
│       ├── core/       # Trading logic & technical analysis engines
│       ├── api/        # IBKR connection & market data handlers
│       ├── models/     # Signal, Trade, and Portfolio data models
│       └── main.py     # Entry point for the trading loop
├── tests/              # Comprehensive pytest suite
├── notebooks/          # Strategy research & data analysis
└── pyproject.toml      # Project configuration & dependencies
```

## 🛠️ Getting Started

### Prerequisites

*   **Python 3.12+**
*   **uv** (Package Manager)
*   **IBKR TWS or IB Gateway** (configured with API access enabled on port 7497/4002)

### Installation

1.  **Initialize the environment**:
    ```bash
    uv sync
    ```

2.  **Configure Environment Variables**:
    Create a `.env` file based on `.env.example`:
    ```bash
    cp .env.example .env
    # Edit .env with your specific API keys and IBKR settings
    ```

## 📈 Execution

To launch the trading floor:

```bash
uv run src/algokitforge/main.py
```

> [!CAUTION]
> **Token Consumption Warning**: This agent runs on a 2-minute cycle and sends comprehensive market data (OHLCV + Technical Indicators) to LLMs for reasoning. Sustained operation will lead to significant API token usage and associated costs. Monitor your OpenAI/Anthropic dashboards closely.

The agent operates on a continuous 2-minute cycle (optimized for day trading), performing the following steps:
1.  **Sync**: Retrieve the latest market data for MNQ and MGC.
2.  **Analyze**: Calculate indicators and generate multi-timeframe reports.
3.  **Reason**: LLM agents evaluate the reports against the core strategy.
4.  **Execute**: Orders are dispatched with pre-defined risk parameters if conditions are met.

## 🧪 Testing

Validation is handled via `pytest`. To run all tests:

```bash
uv run pytest
```

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

### ⚠️ Disclaimer

*Trading futures involves substantial risk of loss and is not appropriate for all investors. Past performance is not indicative of future results. AlgoKitForge is provided for educational and research purposes. Use at your own risk.*

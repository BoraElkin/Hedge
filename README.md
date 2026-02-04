# Hedge — AI-Native Hedge Fund Framework

An AI-powered hedge fund framework that uses LLM agents (Claude, GPT-4) alongside quantitative analysis to generate trading signals, construct portfolios, and execute trades.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLI / Orchestrator                │
├─────────────┬─────────────┬──────────┬──────────────┤
│  Technical  │ Fundamental │Sentiment │    Risk      │
│   Agent     │   Agent     │  Agent   │   Agent      │
│  (TA + LLM) │ (Data+LLM) │(News+LLM)│ (Quant)     │
├─────────────┴─────────────┴──────────┴──────────────┤
│                Portfolio Agent                       │
│         (Signal aggregation + allocation)            │
├─────────────────────────────────────────────────────┤
│               Backtester / Execution                 │
│          (Paper trading / Alpaca broker)              │
├─────────────────────────────────────────────────────┤
│                   Data Layer                         │
│         (yfinance, Finnhub, market data)             │
└─────────────────────────────────────────────────────┘
```

## Agents

| Agent | Input | Method |
|-------|-------|--------|
| **Technical** | OHLCV price data | Computes RSI, MACD, Bollinger Bands, etc. then asks an LLM to interpret |
| **Fundamentals** | P/E, market cap, returns | Passes valuation metrics to LLM for assessment |
| **Sentiment** | News articles | LLM analyzes recent headlines and news for sentiment |
| **Risk** | Price history, SPY correlation | Computes VaR, drawdown, beta, volatility — pure quantitative |
| **Portfolio** | All agent signals | Weighted aggregation into target allocations |

Each agent produces a **Signal** with a direction (strong_buy → strong_sell), confidence (0–1), and reasoning.

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd Hedge
pip install -e ".[dev]"

# Set up API keys
cp .env.example .env
# Edit .env with your keys (at minimum: ANTHROPIC_API_KEY)

# Run analysis on default universe
python main.py analyze

# Analyze specific stocks
python main.py analyze AAPL NVDA TSLA

# Run backtest only
python main.py backtest AAPL MSFT GOOGL --period 1y --capital 100000

# Risk assessment
python main.py risk AAPL TSLA NVDA

# Paper trade (simulate execution)
python main.py trade AAPL MSFT --paper

# Live trade via Alpaca (requires ALPACA_API_KEY)
python main.py trade AAPL MSFT --no-paper
```

## Configuration

All settings are in `.env` (see `.env.example`):

- **ANTHROPIC_API_KEY** — Required for LLM-powered agents (Claude)
- **OPENAI_API_KEY** — Alternative LLM provider
- **FINNHUB_API_KEY** — News/sentiment data (free tier available)
- **ALPACA_API_KEY** — Live/paper trading execution

Market data via yfinance requires no API key.

## Project Structure

```
Hedge/
├── config/
│   └── settings.py          # Pydantic settings (loaded from .env)
├── src/
│   ├── agents/
│   │   ├── base_agent.py     # Base class + LLM integration
│   │   ├── technical_agent.py
│   │   ├── fundamentals_agent.py
│   │   ├── sentiment_agent.py
│   │   ├── risk_agent.py
│   │   └── portfolio_agent.py
│   ├── data/
│   │   ├── market_data.py    # yfinance wrapper
│   │   └── news_data.py      # Finnhub news
│   ├── backtester/
│   │   └── engine.py         # Event-driven backtester
│   ├── execution/
│   │   └── broker.py         # Paper + Alpaca broker
│   ├── utils/
│   │   └── display.py        # Rich terminal output
│   ├── orchestrator.py       # Pipeline coordinator
│   └── cli.py                # Typer CLI
├── tests/
├── main.py
├── pyproject.toml
└── .env.example
```

## How It Works

1. **Data Ingestion** — Market data (yfinance) and news (Finnhub) are fetched for each symbol
2. **Agent Analysis** — Each agent independently analyzes the symbol and produces a Signal
3. **Portfolio Construction** — The Portfolio Agent aggregates signals using weighted scoring and generates target allocations
4. **Backtesting** — Target allocations are backtested against historical data to validate
5. **Execution** — Orders are sent to the broker (paper or live via Alpaca)

## Extending

**Add a new agent:**

```python
from src.agents.base_agent import BaseAgent, Signal

class MyAgent(BaseAgent):
    name = "my_agent"

    def analyze(self, symbol: str) -> Signal:
        # Your analysis logic here
        context = "..."
        raw = self._call_llm("system prompt", context)
        return self._parse_llm_signal(raw, symbol)
```

Then register it in `src/orchestrator.py` and add its weight to `PortfolioAgent.agent_weights`.

## Disclaimer

This is a research framework. It is not financial advice. Use at your own risk. Always start with paper trading.

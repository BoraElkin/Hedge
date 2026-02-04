"""Orchestrator — runs the full AI hedge fund pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config.settings import get_settings
from src.agents.base_agent import Signal
from src.agents.fundamentals_agent import FundamentalsAgent
from src.agents.technical_agent import TechnicalAgent
from src.agents.sentiment_agent import SentimentAgent
from src.agents.risk_agent import RiskAgent
from src.agents.portfolio_agent import PortfolioAgent, PortfolioAllocation
from src.backtester.engine import Backtester, BacktestResult
from src.execution.broker import BaseBroker, PaperBroker, Order
from src.utils.display import display_signals, display_portfolio, display_backtest

console = Console()


@dataclass
class AnalysisResult:
    signals: dict[str, list[Signal]]
    allocations: list[PortfolioAllocation]
    backtest: BacktestResult | None


class HedgeFundOrchestrator:
    """Runs the full analysis pipeline: data -> agents -> portfolio -> execution."""

    def __init__(
        self,
        broker: BaseBroker | None = None,
        universe: list[str] | None = None,
    ) -> None:
        settings = get_settings()
        self._universe = universe or settings.default_universe
        self._broker = broker or PaperBroker()

        # Initialize agents
        self._technical = TechnicalAgent()
        self._fundamentals = FundamentalsAgent()
        self._sentiment = SentimentAgent()
        self._risk = RiskAgent()
        self._portfolio = PortfolioAgent()

    def run_analysis(
        self,
        symbols: list[str] | None = None,
        run_backtest: bool = True,
    ) -> AnalysisResult:
        """Run the full analysis pipeline."""
        symbols = symbols or self._universe

        console.print(f"\n[bold]AI Hedge Fund Analysis[/bold]")
        console.print(f"Universe: {', '.join(symbols)}\n")

        # Phase 1: Gather signals from all agents
        all_signals: dict[str, list[Signal]] = {}
        flat_signals: list[Signal] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            for symbol in symbols:
                task = progress.add_task(f"Analyzing {symbol}...", total=None)
                symbol_signals = self._analyze_symbol(symbol)
                all_signals[symbol] = symbol_signals
                flat_signals.extend(symbol_signals)
                progress.update(task, completed=True)

        # Display signals
        display_signals(flat_signals)

        # Phase 2: Portfolio construction
        console.print("\n[bold]Constructing portfolio...[/bold]")
        allocations = self._portfolio.construct_portfolio(all_signals)
        display_portfolio(allocations)

        # Phase 3: Backtest (optional)
        backtest_result = None
        if run_backtest and allocations:
            console.print("\n[bold]Running backtest...[/bold]")
            target_weights = {a.symbol: a.weight for a in allocations}
            backtester = Backtester()
            try:
                backtest_result = backtester.run(
                    symbols=[a.symbol for a in allocations],
                    target_weights=target_weights,
                )
                display_backtest(backtest_result)
            except Exception as e:
                console.print(f"[red]Backtest failed: {e}[/red]")

        return AnalysisResult(
            signals=all_signals,
            allocations=allocations,
            backtest=backtest_result,
        )

    def execute_trades(self, allocations: list[PortfolioAllocation]) -> list[Order]:
        """Execute trades to reach the target allocation."""
        console.print("\n[bold]Executing trades...[/bold]")

        portfolio_value = self._broker.get_portfolio_value()
        current_positions = self._broker.get_positions()
        orders: list[Order] = []

        for alloc in allocations:
            target_value = portfolio_value * alloc.weight
            current_qty = current_positions.get(alloc.symbol, 0)

            # Get current price for quantity calculation
            from src.data.market_data import MarketDataProvider

            market = MarketDataProvider()
            try:
                snap = market.get_snapshot(alloc.symbol)
                price = snap.current_price
            except Exception:
                console.print(f"[red]Could not get price for {alloc.symbol}, skipping[/red]")
                continue

            current_value = current_qty * price
            diff = target_value - current_value

            if abs(diff) < portfolio_value * 0.005:  # Skip tiny adjustments
                continue

            if diff > 0:
                qty = int(diff / price)
                if qty > 0:
                    order = Order(symbol=alloc.symbol, side="buy", quantity=qty)
                    result = self._broker.submit_order(order)
                    orders.append(result)
                    console.print(f"  BUY  {qty} {alloc.symbol} @ ~${price:.2f} -> {result.status.value}")
            else:
                qty = int(abs(diff) / price)
                if qty > 0:
                    order = Order(symbol=alloc.symbol, side="sell", quantity=qty)
                    result = self._broker.submit_order(order)
                    orders.append(result)
                    console.print(f"  SELL {qty} {alloc.symbol} @ ~${price:.2f} -> {result.status.value}")

        return orders

    def _analyze_symbol(self, symbol: str) -> list[Signal]:
        """Run all agents on a single symbol and collect signals."""
        signals: list[Signal] = []

        # Technical analysis (always available — uses free yfinance data)
        try:
            signals.append(self._technical.analyze(symbol))
        except Exception as e:
            console.print(f"  [dim]Technical agent failed for {symbol}: {e}[/dim]")

        # Fundamental analysis
        try:
            signals.append(self._fundamentals.analyze(symbol))
        except Exception as e:
            console.print(f"  [dim]Fundamentals agent failed for {symbol}: {e}[/dim]")

        # Sentiment analysis (requires news API + LLM)
        try:
            signals.append(self._sentiment.analyze(symbol))
        except Exception as e:
            console.print(f"  [dim]Sentiment agent failed for {symbol}: {e}[/dim]")

        # Risk analysis (always available)
        try:
            signals.append(self._risk.analyze(symbol))
        except Exception as e:
            console.print(f"  [dim]Risk agent failed for {symbol}: {e}[/dim]")

        return signals

"""CLI entrypoint for the AI hedge fund."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="hedge",
    help="AI-native hedge fund framework",
    no_args_is_help=True,
)
console = Console()


@app.command()
def analyze(
    symbols: list[str] = typer.Argument(
        None, help="Symbols to analyze (e.g. AAPL MSFT GOOGL)"
    ),
    backtest: bool = typer.Option(True, "--backtest/--no-backtest", help="Run backtest"),
) -> None:
    """Run AI analysis on a set of symbols."""
    from src.orchestrator import HedgeFundOrchestrator

    orch = HedgeFundOrchestrator()
    orch.run_analysis(symbols=symbols or None, run_backtest=backtest)


@app.command()
def backtest(
    symbols: list[str] = typer.Argument(
        None, help="Symbols to backtest"
    ),
    period: str = typer.Option("1y", help="Lookback period (e.g. 6mo, 1y, 2y)"),
    capital: float = typer.Option(100_000, help="Initial capital"),
) -> None:
    """Run a backtest with equal-weight portfolio."""
    from src.backtester.engine import Backtester
    from src.utils.display import display_backtest
    from config.settings import get_settings

    syms = symbols or get_settings().default_universe[:5]
    weight = 0.9 / len(syms)  # 90% invested, 10% cash
    weights = {s: weight for s in syms}

    console.print(f"[bold]Backtesting equal-weight portfolio[/bold]")
    console.print(f"Symbols: {', '.join(syms)}")
    console.print(f"Period: {period} | Capital: ${capital:,.0f}\n")

    bt = Backtester(initial_capital=capital)
    result = bt.run(syms, weights, period=period)
    display_backtest(result)


@app.command()
def trade(
    symbols: list[str] = typer.Argument(
        None, help="Symbols to trade"
    ),
    paper: bool = typer.Option(True, help="Use paper trading (default: True)"),
) -> None:
    """Run analysis and execute trades (paper mode by default)."""
    from src.orchestrator import HedgeFundOrchestrator
    from src.execution.broker import PaperBroker, AlpacaBroker

    if paper:
        broker = PaperBroker()
        console.print("[yellow]Paper trading mode[/yellow]\n")
    else:
        broker = AlpacaBroker()
        console.print("[red]LIVE trading mode[/red]\n")

    orch = HedgeFundOrchestrator(broker=broker)
    result = orch.run_analysis(symbols=symbols or None)

    if result.allocations:
        if not paper:
            confirm = typer.confirm("Execute live trades?")
            if not confirm:
                raise typer.Abort()
        orch.execute_trades(result.allocations)


@app.command()
def risk(
    symbols: list[str] = typer.Argument(
        None, help="Symbols to assess"
    ),
) -> None:
    """Run risk assessment on symbols."""
    from src.agents.risk_agent import RiskAgent
    from rich.table import Table

    agent = RiskAgent()
    syms = symbols or ["AAPL", "MSFT", "TSLA", "NVDA", "SPY"]

    table = Table(title="Risk Assessment", show_lines=True)
    table.add_column("Symbol", style="bold")
    table.add_column("Vol (Annual)", justify="right")
    table.add_column("VaR 95%", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Beta", justify="right")
    table.add_column("SPY Corr", justify="right")
    table.add_column("Rating")
    table.add_column("Rec. Size", justify="right")

    for sym in syms:
        console.print(f"Assessing {sym}...")
        try:
            assessment = agent.assess_risk(sym)
            rating_color = {
                "low": "green",
                "medium": "yellow",
                "high": "red",
                "extreme": "bold red",
            }.get(assessment.risk_rating, "white")

            table.add_row(
                sym,
                f"{assessment.volatility_annual:.1%}",
                f"{assessment.var_95:.2%}",
                f"{assessment.max_drawdown:.1%}",
                f"{assessment.beta:.2f}" if assessment.beta else "N/A",
                f"{assessment.correlation_to_spy:.2f}",
                f"[{rating_color}]{assessment.risk_rating}[/{rating_color}]",
                f"{assessment.recommended_position_size:.1%}",
            )
        except Exception as e:
            table.add_row(sym, "—", "—", "—", "—", "—", f"[red]Error: {e}[/red]", "—")

    console.print(table)


if __name__ == "__main__":
    app()

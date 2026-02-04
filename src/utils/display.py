"""Rich-powered display utilities for terminal output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.agents.base_agent import Signal, SignalDirection
from src.agents.portfolio_agent import PortfolioAllocation
from src.backtester.engine import BacktestResult

console = Console()


def display_signals(signals: list[Signal]) -> None:
    """Print a table of trading signals."""
    table = Table(title="Agent Signals", show_lines=True)
    table.add_column("Symbol", style="bold")
    table.add_column("Agent")
    table.add_column("Direction")
    table.add_column("Confidence", justify="right")
    table.add_column("Reasoning", max_width=60)

    direction_colors = {
        SignalDirection.STRONG_BUY: "bold green",
        SignalDirection.BUY: "green",
        SignalDirection.HOLD: "yellow",
        SignalDirection.SELL: "red",
        SignalDirection.STRONG_SELL: "bold red",
    }

    for s in signals:
        color = direction_colors.get(s.direction, "white")
        table.add_row(
            s.symbol,
            s.agent_name,
            f"[{color}]{s.direction.value}[/{color}]",
            f"{s.confidence:.0%}",
            s.reasoning[:120],
        )

    console.print(table)


def display_portfolio(allocations: list[PortfolioAllocation]) -> None:
    """Print the target portfolio allocation."""
    table = Table(title="Portfolio Allocation", show_lines=True)
    table.add_column("Symbol", style="bold")
    table.add_column("Weight", justify="right")
    table.add_column("Direction")
    table.add_column("Score", justify="right")
    table.add_column("Reasoning", max_width=60)

    total_weight = 0.0
    for a in allocations:
        total_weight += a.weight
        table.add_row(
            a.symbol,
            f"{a.weight:.1%}",
            a.direction,
            f"{a.composite_score:.3f}",
            a.reasoning[:120],
        )

    table.add_row("CASH", f"{1 - total_weight:.1%}", "—", "—", "")
    console.print(table)


def display_backtest(result: BacktestResult) -> None:
    """Print backtest results."""
    console.print(Panel(result.summary(), title="Backtest Results", border_style="blue"))

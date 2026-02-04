"""Backtesting engine — simulates portfolio performance over historical data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src.data.market_data import MarketDataProvider


@dataclass
class Trade:
    date: datetime
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    price: float
    value: float


@dataclass
class BacktestResult:
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_value: float
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    portfolio_values: pd.Series  # Daily portfolio values
    trades: list[Trade]
    daily_returns: pd.Series

    def summary(self) -> str:
        return (
            f"Backtest Results ({self.start_date:%Y-%m-%d} to {self.end_date:%Y-%m-%d})\n"
            f"{'='*55}\n"
            f"  Initial Capital:    ${self.initial_capital:>12,.2f}\n"
            f"  Final Value:        ${self.final_value:>12,.2f}\n"
            f"  Total Return:       {self.total_return:>12.2%}\n"
            f"  Annualized Return:  {self.annualized_return:>12.2%}\n"
            f"  Sharpe Ratio:       {self.sharpe_ratio:>12.2f}\n"
            f"  Max Drawdown:       {self.max_drawdown:>12.2%}\n"
            f"  Win Rate:           {self.win_rate:>12.2%}\n"
            f"  Total Trades:       {self.total_trades:>12d}\n"
        )


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_price: float

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_price


class Backtester:
    """Event-driven backtester for portfolio strategies."""

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        self._initial_capital = initial_capital
        self._market = MarketDataProvider()

    def run(
        self,
        symbols: list[str],
        target_weights: dict[str, float],
        period: str = "1y",
        rebalance_frequency: int = 20,  # Trading days between rebalances
    ) -> BacktestResult:
        """Run a backtest with fixed target weights, rebalanced periodically.

        Args:
            symbols: Universe of symbols to trade
            target_weights: {symbol: target_weight} — weights should sum to <= 1.0
            period: Lookback period for historical data
            rebalance_frequency: Days between rebalances
        """
        # Fetch price data
        price_data = self._market.get_multiple_price_history(symbols, period=period)
        if not price_data:
            raise ValueError("No price data available for backtesting")

        # Build aligned close price DataFrame
        close_prices = pd.DataFrame({sym: df["Close"] for sym, df in price_data.items()})
        close_prices = close_prices.dropna()

        if close_prices.empty:
            raise ValueError("No overlapping price data for the given symbols")

        # Initialize state
        cash = self._initial_capital
        positions: dict[str, Position] = {}
        trades: list[Trade] = []
        portfolio_values: list[float] = []
        dates: list[datetime] = []

        for day_idx, (date, prices) in enumerate(close_prices.iterrows()):
            # Rebalance on the first day and every N days
            if day_idx % rebalance_frequency == 0:
                cash, new_trades = self._rebalance(
                    date, prices, positions, cash, target_weights
                )
                trades.extend(new_trades)

            # Mark to market
            portfolio_val = cash
            for sym, pos in positions.items():
                if sym in prices.index:
                    portfolio_val += pos.quantity * prices[sym]

            portfolio_values.append(portfolio_val)
            dates.append(date)

        # Compute results
        values_series = pd.Series(portfolio_values, index=dates)
        daily_returns = values_series.pct_change().dropna()

        final_value = portfolio_values[-1]
        total_return = (final_value / self._initial_capital) - 1
        n_days = len(portfolio_values)
        annualized_return = (1 + total_return) ** (252 / max(n_days, 1)) - 1

        sharpe = (
            float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))
            if daily_returns.std() > 0
            else 0.0
        )

        cummax = values_series.cummax()
        drawdowns = values_series / cummax - 1
        max_dd = float(drawdowns.min())

        # Win rate based on trades
        pnl_per_trade = self._compute_trade_pnl(trades)
        win_rate = sum(1 for p in pnl_per_trade if p > 0) / max(len(pnl_per_trade), 1)

        return BacktestResult(
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=self._initial_capital,
            final_value=final_value,
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=len(trades),
            portfolio_values=values_series,
            trades=trades,
            daily_returns=daily_returns,
        )

    def _rebalance(
        self,
        date: datetime,
        prices: pd.Series,
        positions: dict[str, Position],
        cash: float,
        target_weights: dict[str, float],
    ) -> tuple[float, list[Trade]]:
        """Rebalance portfolio to target weights."""
        trades: list[Trade] = []

        # Current portfolio value
        port_value = cash
        for sym, pos in positions.items():
            if sym in prices.index:
                port_value += pos.quantity * prices[sym]

        # Sell positions not in target or overweight
        for sym in list(positions.keys()):
            if sym not in target_weights or target_weights.get(sym, 0) == 0:
                if sym in prices.index:
                    pos = positions.pop(sym)
                    sell_value = pos.quantity * prices[sym]
                    cash += sell_value
                    trades.append(Trade(date, sym, "sell", pos.quantity, prices[sym], sell_value))

        # Compute target positions
        for sym, target_w in target_weights.items():
            if sym not in prices.index or target_w <= 0:
                continue

            target_value = port_value * target_w
            current_value = (
                positions[sym].quantity * prices[sym] if sym in positions else 0
            )
            diff_value = target_value - current_value

            if abs(diff_value) < port_value * 0.005:  # Skip if diff < 0.5%
                continue

            if diff_value > 0:
                # Buy
                qty = diff_value / prices[sym]
                cost = qty * prices[sym]
                if cost <= cash:
                    cash -= cost
                    if sym in positions:
                        old = positions[sym]
                        total_qty = old.quantity + qty
                        avg = (old.cost_basis + cost) / total_qty
                        positions[sym] = Position(sym, total_qty, avg)
                    else:
                        positions[sym] = Position(sym, qty, prices[sym])
                    trades.append(Trade(date, sym, "buy", qty, prices[sym], cost))
            else:
                # Sell
                qty = min(abs(diff_value) / prices[sym], positions.get(sym, Position(sym, 0, 0)).quantity)
                if qty > 0 and sym in positions:
                    sell_value = qty * prices[sym]
                    cash += sell_value
                    positions[sym] = Position(
                        sym,
                        positions[sym].quantity - qty,
                        positions[sym].avg_price,
                    )
                    if positions[sym].quantity <= 0.001:
                        del positions[sym]
                    trades.append(Trade(date, sym, "sell", qty, prices[sym], sell_value))

        return cash, trades

    def _compute_trade_pnl(self, trades: list[Trade]) -> list[float]:
        """Approximate P&L per round-trip."""
        buys: dict[str, list[Trade]] = {}
        pnl: list[float] = []

        for t in trades:
            if t.side == "buy":
                buys.setdefault(t.symbol, []).append(t)
            elif t.side == "sell" and t.symbol in buys and buys[t.symbol]:
                buy_trade = buys[t.symbol].pop(0)
                pnl.append((t.price - buy_trade.price) * min(t.quantity, buy_trade.quantity))

        return pnl

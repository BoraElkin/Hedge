"""Market data provider — wraps yfinance for historical OHLCV and fundamentals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class TickerSnapshot:
    """Point-in-time snapshot of a ticker's key data."""

    symbol: str
    current_price: float
    market_cap: float | None
    pe_ratio: float | None
    forward_pe: float | None
    dividend_yield: float | None
    beta: float | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    avg_volume: int | None
    sector: str | None
    industry: str | None


class MarketDataProvider:
    """Fetch market data via yfinance (free, no API key required)."""

    def get_price_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return OHLCV DataFrame for *symbol*."""
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            raise ValueError(f"No price data returned for {symbol}")
        return df

    def get_multiple_price_history(
        self,
        symbols: list[str],
        period: str = "1y",
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Return OHLCV DataFrames keyed by symbol."""
        data = yf.download(symbols, period=period, interval=interval, group_by="ticker")
        result: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            try:
                df = data[sym].dropna()
                if not df.empty:
                    result[sym] = df
            except (KeyError, TypeError):
                continue
        return result

    def get_snapshot(self, symbol: str) -> TickerSnapshot:
        """Return a fundamental snapshot for *symbol*."""
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return TickerSnapshot(
            symbol=symbol,
            current_price=info.get("currentPrice") or info.get("regularMarketPrice", 0.0),
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            dividend_yield=info.get("dividendYield"),
            beta=info.get("beta"),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            avg_volume=info.get("averageVolume"),
            sector=info.get("sector"),
            industry=info.get("industry"),
        )

    def get_snapshots(self, symbols: list[str]) -> dict[str, TickerSnapshot]:
        """Return snapshots for multiple symbols (skips failures)."""
        snapshots: dict[str, TickerSnapshot] = {}
        for sym in symbols:
            try:
                snapshots[sym] = self.get_snapshot(sym)
            except Exception:
                continue
        return snapshots

    def get_recent_returns(
        self,
        symbol: str,
        lookback_days: int = 30,
    ) -> dict[str, float]:
        """Compute recent return statistics."""
        df = self.get_price_history(symbol, period="3mo")
        close = df["Close"]
        recent = close.iloc[-lookback_days:]
        returns = recent.pct_change().dropna()
        return {
            "total_return": float((recent.iloc[-1] / recent.iloc[0]) - 1),
            "mean_daily_return": float(returns.mean()),
            "volatility": float(returns.std()),
            "sharpe_approx": float(returns.mean() / returns.std()) if returns.std() > 0 else 0.0,
            "max_drawdown": float((recent / recent.cummax() - 1).min()),
        }

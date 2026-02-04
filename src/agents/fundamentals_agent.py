"""Fundamentals analysis agent — evaluates valuation, growth, and quality metrics."""

from __future__ import annotations

from src.agents.base_agent import BaseAgent, Signal
from src.data.market_data import MarketDataProvider


class FundamentalsAgent(BaseAgent):
    name = "fundamentals"

    def __init__(self) -> None:
        super().__init__()
        self._market = MarketDataProvider()

    def analyze(self, symbol: str) -> Signal:
        snapshot = self._market.get_snapshot(symbol)
        returns = self._market.get_recent_returns(symbol, lookback_days=60)

        context = self._format_fundamentals(snapshot, returns)

        system_prompt = (
            "You are a fundamental equity analyst at a top hedge fund. "
            "Evaluate the following fundamental data and recent performance metrics "
            "to determine whether this stock is undervalued, fairly valued, or overvalued.\n\n"
            "Consider: P/E ratios, market cap, dividend yield, beta, "
            "52-week range positioning, and recent return characteristics.\n\n"
            "Respond ONLY with a JSON object:\n"
            '{"direction": "strong_buy|buy|hold|sell|strong_sell", '
            '"confidence": 0.0-1.0, "reasoning": "..."}'
        )

        raw = self._call_llm(system_prompt, context)
        return self._parse_llm_signal(raw, symbol)

    def _format_fundamentals(self, snapshot, returns: dict) -> str:
        lines = [
            f"Fundamental data for {snapshot.symbol}:",
            f"  Sector: {snapshot.sector}",
            f"  Industry: {snapshot.industry}",
            f"  Current Price: ${snapshot.current_price:.2f}",
            f"  Market Cap: ${snapshot.market_cap:,.0f}" if snapshot.market_cap else "  Market Cap: N/A",
            f"  Trailing P/E: {snapshot.pe_ratio:.2f}" if snapshot.pe_ratio else "  Trailing P/E: N/A",
            f"  Forward P/E: {snapshot.forward_pe:.2f}" if snapshot.forward_pe else "  Forward P/E: N/A",
            f"  Dividend Yield: {snapshot.dividend_yield:.2%}" if snapshot.dividend_yield else "  Dividend Yield: N/A",
            f"  Beta: {snapshot.beta:.2f}" if snapshot.beta else "  Beta: N/A",
            f"  52-Week High: ${snapshot.fifty_two_week_high:.2f}" if snapshot.fifty_two_week_high else "  52-Week High: N/A",
            f"  52-Week Low: ${snapshot.fifty_two_week_low:.2f}" if snapshot.fifty_two_week_low else "  52-Week Low: N/A",
            f"  Avg Volume: {snapshot.avg_volume:,}" if snapshot.avg_volume else "  Avg Volume: N/A",
            "",
            "Recent performance (60 days):",
            f"  Total Return: {returns['total_return']:.2%}",
            f"  Mean Daily Return: {returns['mean_daily_return']:.4%}",
            f"  Volatility (daily): {returns['volatility']:.4%}",
            f"  Sharpe (approx): {returns['sharpe_approx']:.2f}",
            f"  Max Drawdown: {returns['max_drawdown']:.2%}",
        ]
        return "\n".join(lines)

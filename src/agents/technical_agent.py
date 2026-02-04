"""Technical analysis agent — uses price/volume indicators + LLM interpretation."""

from __future__ import annotations

import ta
import pandas as pd

from src.agents.base_agent import BaseAgent, Signal
from src.data.market_data import MarketDataProvider


class TechnicalAgent(BaseAgent):
    name = "technical"

    def __init__(self) -> None:
        super().__init__()
        self._market = MarketDataProvider()

    def analyze(self, symbol: str) -> Signal:
        df = self._market.get_price_history(symbol, period="6mo")
        indicators = self._compute_indicators(df)
        indicator_text = self._format_indicators(indicators, symbol)

        system_prompt = (
            "You are a quantitative technical analyst at a top hedge fund. "
            "Analyze the following technical indicators and produce a trading signal.\n\n"
            "Respond ONLY with a JSON object:\n"
            '{"direction": "strong_buy|buy|hold|sell|strong_sell", '
            '"confidence": 0.0-1.0, "reasoning": "..."}'
        )

        raw = self._call_llm(system_prompt, indicator_text)
        return self._parse_llm_signal(raw, symbol)

    def _compute_indicators(self, df: pd.DataFrame) -> dict[str, float | str]:
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        # Trend indicators
        sma_20 = ta.trend.sma_indicator(close, window=20)
        sma_50 = ta.trend.sma_indicator(close, window=50)
        ema_12 = ta.trend.ema_indicator(close, window=12)
        ema_26 = ta.trend.ema_indicator(close, window=26)
        macd_line = ta.trend.macd(close)
        macd_signal = ta.trend.macd_signal(close)

        # Momentum
        rsi = ta.momentum.rsi(close, window=14)
        stoch = ta.momentum.stoch(high, low, close)

        # Volatility
        bb_high = ta.volatility.bollinger_hband(close)
        bb_low = ta.volatility.bollinger_lband(close)
        atr = ta.volatility.average_true_range(high, low, close)

        # Volume
        obv = ta.volume.on_balance_volume(close, volume)

        current = close.iloc[-1]
        return {
            "current_price": float(current),
            "sma_20": float(sma_20.iloc[-1]),
            "sma_50": float(sma_50.iloc[-1]),
            "ema_12": float(ema_12.iloc[-1]),
            "ema_26": float(ema_26.iloc[-1]),
            "macd": float(macd_line.iloc[-1]),
            "macd_signal": float(macd_signal.iloc[-1]),
            "rsi_14": float(rsi.iloc[-1]),
            "stochastic": float(stoch.iloc[-1]),
            "bollinger_upper": float(bb_high.iloc[-1]),
            "bollinger_lower": float(bb_low.iloc[-1]),
            "atr_14": float(atr.iloc[-1]),
            "obv": float(obv.iloc[-1]),
            "price_vs_sma20": "above" if current > sma_20.iloc[-1] else "below",
            "price_vs_sma50": "above" if current > sma_50.iloc[-1] else "below",
            "macd_crossover": "bullish" if macd_line.iloc[-1] > macd_signal.iloc[-1] else "bearish",
            "volume_trend": "increasing" if volume.iloc[-1] > volume.rolling(20).mean().iloc[-1] else "decreasing",
        }

    def _format_indicators(self, indicators: dict, symbol: str) -> str:
        lines = [f"Technical indicators for {symbol}:", ""]
        for key, val in indicators.items():
            label = key.replace("_", " ").title()
            if isinstance(val, float):
                lines.append(f"  {label}: {val:.4f}")
            else:
                lines.append(f"  {label}: {val}")
        return "\n".join(lines)

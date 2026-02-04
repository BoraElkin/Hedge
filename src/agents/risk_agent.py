"""Risk management agent — evaluates position-level and portfolio-level risk."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.agents.base_agent import BaseAgent, Signal, SignalDirection
from src.data.market_data import MarketDataProvider


@dataclass
class RiskAssessment:
    symbol: str
    volatility_annual: float
    var_95: float  # Value at Risk (95%)
    max_drawdown: float
    beta: float | None
    correlation_to_spy: float
    risk_rating: str  # "low", "medium", "high", "extreme"
    recommended_position_size: float  # As fraction of portfolio


class RiskAgent(BaseAgent):
    name = "risk"

    def __init__(self) -> None:
        super().__init__()
        self._market = MarketDataProvider()

    def analyze(self, symbol: str) -> Signal:
        assessment = self.assess_risk(symbol)
        return self._risk_to_signal(assessment)

    def assess_risk(self, symbol: str) -> RiskAssessment:
        """Full risk assessment for a single symbol."""
        df = self._market.get_price_history(symbol, period="1y")
        spy_df = self._market.get_price_history("SPY", period="1y")

        returns = df["Close"].pct_change().dropna()
        spy_returns = spy_df["Close"].pct_change().dropna()

        # Align dates
        aligned = pd.DataFrame({"stock": returns, "spy": spy_returns}).dropna()

        # Annualized volatility
        vol_annual = float(aligned["stock"].std() * np.sqrt(252))

        # VaR 95%
        var_95 = float(np.percentile(aligned["stock"], 5))

        # Max drawdown
        cumulative = (1 + aligned["stock"]).cumprod()
        max_dd = float((cumulative / cumulative.cummax() - 1).min())

        # Beta
        cov = aligned.cov()
        beta = float(cov.loc["stock", "spy"] / cov.loc["spy", "spy"]) if cov.loc["spy", "spy"] > 0 else None

        # Correlation to SPY
        corr = float(aligned["stock"].corr(aligned["spy"]))

        # Risk rating
        if vol_annual > 0.60:
            risk_rating = "extreme"
        elif vol_annual > 0.40:
            risk_rating = "high"
        elif vol_annual > 0.20:
            risk_rating = "medium"
        else:
            risk_rating = "low"

        # Position sizing (inverse volatility targeting 2% risk)
        target_risk = 0.02
        recommended_size = min(target_risk / vol_annual, 0.10) if vol_annual > 0 else 0.05

        return RiskAssessment(
            symbol=symbol,
            volatility_annual=vol_annual,
            var_95=var_95,
            max_drawdown=max_dd,
            beta=beta,
            correlation_to_spy=corr,
            risk_rating=risk_rating,
            recommended_position_size=recommended_size,
        )

    def _risk_to_signal(self, assessment: RiskAssessment) -> Signal:
        """Convert risk assessment into a risk-adjusted signal."""
        # Higher risk = lower confidence, more cautious signal
        risk_penalty = {
            "low": 0.0,
            "medium": 0.1,
            "high": 0.3,
            "extreme": 0.5,
        }
        penalty = risk_penalty.get(assessment.risk_rating, 0.3)

        if assessment.risk_rating == "extreme":
            direction = SignalDirection.SELL
        elif assessment.risk_rating == "high":
            direction = SignalDirection.HOLD
        else:
            direction = SignalDirection.BUY

        return Signal(
            symbol=assessment.symbol,
            direction=direction,
            confidence=max(0.1, 1.0 - penalty),
            agent_name=self.name,
            reasoning=(
                f"Risk rating: {assessment.risk_rating}. "
                f"Annual vol: {assessment.volatility_annual:.1%}, "
                f"VaR(95%): {assessment.var_95:.2%}, "
                f"Max DD: {assessment.max_drawdown:.1%}, "
                f"Beta: {assessment.beta:.2f}, "
                f"SPY corr: {assessment.correlation_to_spy:.2f}. "
                f"Recommended position size: {assessment.recommended_position_size:.1%}"
            ),
            metadata={
                "volatility_annual": assessment.volatility_annual,
                "var_95": assessment.var_95,
                "max_drawdown": assessment.max_drawdown,
                "beta": assessment.beta,
                "correlation_to_spy": assessment.correlation_to_spy,
                "recommended_position_size": assessment.recommended_position_size,
            },
        )

"""Portfolio construction agent — synthesizes signals from all agents into allocations."""

from __future__ import annotations

from dataclasses import dataclass

from src.agents.base_agent import BaseAgent, Signal, SignalDirection


@dataclass
class PortfolioAllocation:
    symbol: str
    weight: float  # Target weight in portfolio (0.0–1.0)
    direction: str  # "long" or "flat"
    composite_score: float
    reasoning: str


class PortfolioAgent(BaseAgent):
    """Combines signals from multiple agents into a portfolio allocation."""

    name = "portfolio"

    # Weights for each agent type when combining signals
    agent_weights: dict[str, float] = {
        "technical": 0.25,
        "fundamentals": 0.30,
        "sentiment": 0.20,
        "risk": 0.25,
    }

    def analyze(self, symbol: str) -> Signal:
        # This agent works differently — it combines other signals
        # See `construct_portfolio` for the main entry point
        raise NotImplementedError("Use construct_portfolio() instead")

    def construct_portfolio(
        self,
        signals_by_symbol: dict[str, list[Signal]],
        max_positions: int = 10,
        cash_buffer: float = 0.05,
    ) -> list[PortfolioAllocation]:
        """Build portfolio from multi-agent signals.

        Args:
            signals_by_symbol: {symbol: [signal_from_each_agent]}
            max_positions: Maximum number of positions
            cash_buffer: Minimum cash allocation (e.g. 0.05 = 5%)
        """
        scored: list[tuple[str, float, str]] = []

        for symbol, signals in signals_by_symbol.items():
            composite = self._compute_composite_score(signals)
            reasoning = self._summarize_signals(signals)
            scored.append((symbol, composite, reasoning))

        # Sort by composite score (descending) and take top N
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:max_positions]

        # Only allocate to positive-scoring symbols
        positive = [(sym, score, reason) for sym, score, reason in top if score > 0]

        if not positive:
            return []

        # Allocate using score-weighted scheme
        total_score = sum(s for _, s, _ in positive)
        investable = 1.0 - cash_buffer

        allocations: list[PortfolioAllocation] = []
        for sym, score, reason in positive:
            raw_weight = (score / total_score) * investable if total_score > 0 else 0
            # Cap individual position at 15%
            weight = min(raw_weight, 0.15)
            allocations.append(
                PortfolioAllocation(
                    symbol=sym,
                    weight=weight,
                    direction="long",
                    composite_score=score,
                    reasoning=reason,
                )
            )

        # Normalize weights to sum to investable amount
        total_weight = sum(a.weight for a in allocations)
        if total_weight > 0:
            scale = investable / total_weight
            for a in allocations:
                a.weight = min(a.weight * scale, 0.15)

        return allocations

    def _compute_composite_score(self, signals: list[Signal]) -> float:
        """Weighted average of agent signals."""
        total_weight = 0.0
        weighted_score = 0.0

        for signal in signals:
            agent_w = self.agent_weights.get(signal.agent_name, 0.1)
            weighted_score += signal.numeric_score * agent_w
            total_weight += agent_w

        return weighted_score / total_weight if total_weight > 0 else 0.0

    def _summarize_signals(self, signals: list[Signal]) -> str:
        parts = []
        for s in signals:
            parts.append(f"[{s.agent_name}] {s.direction.value} ({s.confidence:.0%}): {s.reasoning[:100]}")
        return " | ".join(parts)

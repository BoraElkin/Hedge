"""Unit tests for agent framework."""

from __future__ import annotations

import json

from src.agents.base_agent import BaseAgent, Signal, SignalDirection
from src.agents.portfolio_agent import PortfolioAgent


class MockAgent(BaseAgent):
    name = "mock"

    def analyze(self, symbol: str) -> Signal:
        return Signal(
            symbol=symbol,
            direction=SignalDirection.BUY,
            confidence=0.8,
            agent_name=self.name,
            reasoning="Mock signal for testing",
        )


def test_signal_numeric_score():
    signal = Signal(
        symbol="AAPL",
        direction=SignalDirection.BUY,
        confidence=0.8,
        agent_name="test",
        reasoning="test",
    )
    assert signal.numeric_score == 0.5 * 0.8  # BUY=0.5, confidence=0.8


def test_signal_strong_buy_score():
    signal = Signal(
        symbol="AAPL",
        direction=SignalDirection.STRONG_BUY,
        confidence=1.0,
        agent_name="test",
        reasoning="test",
    )
    assert signal.numeric_score == 1.0


def test_signal_sell_score():
    signal = Signal(
        symbol="AAPL",
        direction=SignalDirection.SELL,
        confidence=0.6,
        agent_name="test",
        reasoning="test",
    )
    assert signal.numeric_score == -0.5 * 0.6


def test_signal_hold_score():
    signal = Signal(
        symbol="AAPL",
        direction=SignalDirection.HOLD,
        confidence=0.9,
        agent_name="test",
        reasoning="test",
    )
    assert signal.numeric_score == 0.0


def test_parse_llm_signal_valid_json():
    agent = MockAgent()
    raw = json.dumps({
        "direction": "strong_buy",
        "confidence": 0.85,
        "reasoning": "Strong momentum and improving fundamentals",
    })
    signal = agent._parse_llm_signal(raw, "AAPL")
    assert signal.direction == SignalDirection.STRONG_BUY
    assert signal.confidence == 0.85
    assert "momentum" in signal.reasoning


def test_parse_llm_signal_markdown_json():
    agent = MockAgent()
    raw = '```json\n{"direction": "sell", "confidence": 0.7, "reasoning": "Weak"}\n```'
    signal = agent._parse_llm_signal(raw, "MSFT")
    assert signal.direction == SignalDirection.SELL
    assert signal.confidence == 0.7


def test_parse_llm_signal_invalid_json():
    agent = MockAgent()
    raw = "I think this stock looks good but I'm not sure"
    signal = agent._parse_llm_signal(raw, "TSLA")
    assert signal.direction == SignalDirection.HOLD
    assert signal.confidence == 0.3


def test_parse_llm_signal_clamps_confidence():
    agent = MockAgent()
    raw = json.dumps({"direction": "buy", "confidence": 5.0, "reasoning": "Very confident"})
    signal = agent._parse_llm_signal(raw, "AAPL")
    assert signal.confidence == 1.0


def test_portfolio_construction():
    portfolio_agent = PortfolioAgent()

    signals = {
        "AAPL": [
            Signal("AAPL", SignalDirection.BUY, 0.8, "technical", "Good momentum"),
            Signal("AAPL", SignalDirection.STRONG_BUY, 0.9, "fundamentals", "Undervalued"),
            Signal("AAPL", SignalDirection.BUY, 0.7, "sentiment", "Positive news"),
            Signal("AAPL", SignalDirection.BUY, 0.85, "risk", "Low risk"),
        ],
        "TSLA": [
            Signal("TSLA", SignalDirection.SELL, 0.6, "technical", "Weak"),
            Signal("TSLA", SignalDirection.HOLD, 0.5, "fundamentals", "Expensive"),
            Signal("TSLA", SignalDirection.SELL, 0.7, "sentiment", "Negative"),
            Signal("TSLA", SignalDirection.SELL, 0.8, "risk", "High vol"),
        ],
    }

    allocations = portfolio_agent.construct_portfolio(signals)
    symbols = [a.symbol for a in allocations]

    # AAPL should be in portfolio (positive score), TSLA should not
    assert "AAPL" in symbols
    assert "TSLA" not in symbols

    # Weights should be positive and <= 15%
    for a in allocations:
        assert 0 < a.weight <= 0.15


def test_portfolio_empty_signals():
    portfolio_agent = PortfolioAgent()
    allocations = portfolio_agent.construct_portfolio({})
    assert allocations == []


def test_portfolio_all_negative_signals():
    portfolio_agent = PortfolioAgent()
    signals = {
        "BAD": [
            Signal("BAD", SignalDirection.STRONG_SELL, 0.9, "technical", "Terrible"),
            Signal("BAD", SignalDirection.SELL, 0.8, "fundamentals", "Overvalued"),
        ],
    }
    allocations = portfolio_agent.construct_portfolio(signals)
    assert allocations == []

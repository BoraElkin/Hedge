"""Base agent that all AI analyst agents inherit from."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import anthropic
import openai

from config.settings import get_settings


class SignalDirection(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class Signal:
    """A trading signal produced by an agent."""

    symbol: str
    direction: SignalDirection
    confidence: float  # 0.0 – 1.0
    agent_name: str
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def numeric_score(self) -> float:
        """Map direction to a -1..+1 score, weighted by confidence."""
        direction_map = {
            SignalDirection.STRONG_BUY: 1.0,
            SignalDirection.BUY: 0.5,
            SignalDirection.HOLD: 0.0,
            SignalDirection.SELL: -0.5,
            SignalDirection.STRONG_SELL: -1.0,
        }
        return direction_map[self.direction] * self.confidence


class BaseAgent(ABC):
    """Abstract base class for all AI analyst agents."""

    name: str = "base"

    def __init__(self) -> None:
        self._settings = get_settings()

    @abstractmethod
    def analyze(self, symbol: str) -> Signal:
        """Produce a signal for *symbol*."""

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the configured LLM and return the text response."""
        provider = self._settings.default_llm_provider

        if provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt)
        elif provider == "openai":
            return self._call_openai(system_prompt, user_prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        client = anthropic.Anthropic(api_key=self._settings.anthropic_api_key)
        message = client.messages.create(
            model=self._settings.default_model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        client = openai.OpenAI(api_key=self._settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2048,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def _parse_llm_signal(self, raw: str, symbol: str) -> Signal:
        """Parse a JSON signal block from LLM output.

        Expected JSON shape:
        {
            "direction": "buy",
            "confidence": 0.75,
            "reasoning": "..."
        }
        """
        # Extract JSON from the response (handle markdown code blocks)
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: treat entire response as reasoning, default to HOLD
            return Signal(
                symbol=symbol,
                direction=SignalDirection.HOLD,
                confidence=0.3,
                agent_name=self.name,
                reasoning=raw[:500],
            )

        direction_str = data.get("direction", "hold").lower().replace(" ", "_")
        try:
            direction = SignalDirection(direction_str)
        except ValueError:
            direction = SignalDirection.HOLD

        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))

        return Signal(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            agent_name=self.name,
            reasoning=data.get("reasoning", ""),
            metadata=data.get("metadata", {}),
        )

"""Broker abstraction layer — paper trading and Alpaca integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from config.settings import get_settings


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"  # "market" or "limit"
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_price: float | None = None
    filled_at: datetime | None = None
    order_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseBroker(ABC):
    """Abstract broker interface."""

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit an order and return it with updated status."""

    @abstractmethod
    def get_positions(self) -> dict[str, float]:
        """Return current positions as {symbol: quantity}."""

    @abstractmethod
    def get_portfolio_value(self) -> float:
        """Return total portfolio value."""

    @abstractmethod
    def get_cash(self) -> float:
        """Return available cash."""


class PaperBroker(BaseBroker):
    """In-memory paper trading broker for simulation."""

    def __init__(self, initial_cash: float = 100_000.0) -> None:
        self._cash = initial_cash
        self._positions: dict[str, float] = {}
        self._orders: list[Order] = []

    def submit_order(self, order: Order) -> Order:
        from src.data.market_data import MarketDataProvider

        market = MarketDataProvider()
        snapshot = market.get_snapshot(order.symbol)
        price = snapshot.current_price

        if order.side == "buy":
            cost = price * order.quantity
            if cost > self._cash:
                order.status = OrderStatus.REJECTED
                order.metadata["reason"] = "Insufficient cash"
                return order
            self._cash -= cost
            self._positions[order.symbol] = self._positions.get(order.symbol, 0) + order.quantity
        elif order.side == "sell":
            held = self._positions.get(order.symbol, 0)
            if order.quantity > held:
                order.status = OrderStatus.REJECTED
                order.metadata["reason"] = "Insufficient shares"
                return order
            self._cash += price * order.quantity
            self._positions[order.symbol] = held - order.quantity
            if self._positions[order.symbol] <= 0:
                del self._positions[order.symbol]

        order.status = OrderStatus.FILLED
        order.filled_price = price
        order.filled_at = datetime.now()
        self._orders.append(order)
        return order

    def get_positions(self) -> dict[str, float]:
        return dict(self._positions)

    def get_portfolio_value(self) -> float:
        from src.data.market_data import MarketDataProvider

        market = MarketDataProvider()
        total = self._cash
        for sym, qty in self._positions.items():
            try:
                snap = market.get_snapshot(sym)
                total += snap.current_price * qty
            except Exception:
                pass
        return total

    def get_cash(self) -> float:
        return self._cash


class AlpacaBroker(BaseBroker):
    """Live/paper broker using Alpaca Markets API."""

    def __init__(self) -> None:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest

        settings = get_settings()
        self._client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=("paper" in settings.alpaca_base_url),
        )
        self._OrderSide = OrderSide
        self._TimeInForce = TimeInForce
        self._MarketOrderRequest = MarketOrderRequest
        self._LimitOrderRequest = LimitOrderRequest

    def submit_order(self, order: Order) -> Order:
        side = self._OrderSide.BUY if order.side == "buy" else self._OrderSide.SELL

        if order.order_type == "limit" and order.limit_price:
            req = self._LimitOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=self._TimeInForce.DAY,
                limit_price=order.limit_price,
            )
        else:
            req = self._MarketOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=self._TimeInForce.DAY,
            )

        result = self._client.submit_order(req)
        order.order_id = str(result.id)
        order.status = OrderStatus.PENDING  # Alpaca fills asynchronously
        return order

    def get_positions(self) -> dict[str, float]:
        positions = self._client.get_all_positions()
        return {p.symbol: float(p.qty) for p in positions}

    def get_portfolio_value(self) -> float:
        account = self._client.get_account()
        return float(account.portfolio_value)

    def get_cash(self) -> float:
        account = self._client.get_account()
        return float(account.cash)

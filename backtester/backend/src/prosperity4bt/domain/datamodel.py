from __future__ import annotations

import json
from dataclasses import dataclass, field
from json import JSONEncoder

from prosperity4bt.domain.types import ObservationValue, Position, Product, Symbol, Time, UserId


@dataclass
class Listing:
    symbol: Symbol
    product: Product
    denomination: str


@dataclass
class ConversionObservation:
    bidPrice: float
    askPrice: float
    transportFees: float
    exportTariff: float
    importTariff: float
    sugarPrice: float = 0.0
    sunlightIndex: float = 0.0


@dataclass
class Observation:
    plainValueObservations: dict[Product, ObservationValue]
    conversionObservations: dict[Product, ConversionObservation]

    def __str__(self) -> str:
        return (
            "(plainValueObservations: "
            + json.dumps(self.plainValueObservations, default=str, sort_keys=True)
            + ", conversionObservations: "
            + json.dumps(
                {key: value.__dict__ for key, value in self.conversionObservations.items()},
                default=str,
                sort_keys=True,
            )
            + ")"
        )


@dataclass
class Order:
    symbol: Symbol
    price: int
    quantity: int

    def __str__(self) -> str:
        return f"({self.symbol}, {self.price}, {self.quantity})"

    def __repr__(self) -> str:
        return str(self)


@dataclass
class OrderDepth:
    buy_orders: dict[int, int] = field(default_factory=dict)
    sell_orders: dict[int, int] = field(default_factory=dict)


@dataclass
class Trade:
    symbol: Symbol
    price: int
    quantity: int
    buyer: UserId | None = None
    seller: UserId | None = None
    timestamp: int = 0

    def __str__(self) -> str:
        return (
            "("
            + self.symbol
            + ", "
            + str(self.buyer or "")
            + " << "
            + str(self.seller or "")
            + ", "
            + str(self.price)
            + ", "
            + str(self.quantity)
            + ", "
            + str(self.timestamp)
            + ")"
        )

    def __repr__(self) -> str:
        return str(self)


@dataclass
class TradingState:
    traderData: str
    timestamp: Time
    listings: dict[Symbol, Listing]
    order_depths: dict[Symbol, OrderDepth]
    own_trades: dict[Symbol, list[Trade]]
    market_trades: dict[Symbol, list[Trade]]
    position: dict[Product, Position]
    observations: Observation

    def toJSON(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True)


class ProsperityEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__

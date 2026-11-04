from __future__ import annotations

from prosperity4bt.data.loaders_observations import ObservationSnapshot
from prosperity4bt.data.loaders_prices import PriceSnapshot
from prosperity4bt.domain.datamodel import (
    ConversionObservation,
    Listing,
    Observation,
    OrderDepth,
    Trade,
    TradingState,
)


def build_state(
    timestamp: int,
    snapshots_by_product: dict[str, PriceSnapshot],
    observations_by_product: dict[str, ObservationSnapshot],
    previous_own_trades: dict[str, list[Trade]],
    previous_market_trades: dict[str, list[Trade]],
    positions: dict[str, int],
    trader_data: str,
) -> TradingState:
    listings: dict[str, Listing] = {}
    order_depths: dict[str, OrderDepth] = {}
    plain_observations: dict[str, float] = {}
    conversion_observations: dict[str, ConversionObservation] = {}

    for product, snapshot in snapshots_by_product.items():
        listings[product] = Listing(symbol=product, product=product, denomination="XIRECS")
        order_depths[product] = _build_depth(snapshot)
        plain_observations[product] = snapshot.mid_price

    for product, obs in observations_by_product.items():
        conversion_observations[product] = ConversionObservation(
            bidPrice=obs.bidPrice,
            askPrice=obs.askPrice,
            transportFees=obs.transportFees,
            exportTariff=obs.exportTariff,
            importTariff=obs.importTariff,
            sugarPrice=obs.sugarPrice,
            sunlightIndex=obs.sunlightIndex,
        )

    return TradingState(
        traderData=trader_data,
        timestamp=timestamp,
        listings=listings,
        order_depths=order_depths,
        own_trades={symbol: list(trades) for symbol, trades in previous_own_trades.items()},
        market_trades={symbol: list(trades) for symbol, trades in previous_market_trades.items()},
        position={product: int(size) for product, size in positions.items()},
        observations=Observation(
            plainValueObservations=plain_observations,
            conversionObservations=conversion_observations,
        ),
    )


def _build_depth(snapshot: PriceSnapshot) -> OrderDepth:
    buy_orders = {
        snapshot.bid_prices[index]: snapshot.bid_volumes[index]
        for index in range(min(len(snapshot.bid_prices), len(snapshot.bid_volumes)))
    }
    sell_orders = {
        snapshot.ask_prices[index]: -abs(snapshot.ask_volumes[index])
        for index in range(min(len(snapshot.ask_prices), len(snapshot.ask_volumes)))
    }
    return OrderDepth(buy_orders=buy_orders, sell_orders=sell_orders)

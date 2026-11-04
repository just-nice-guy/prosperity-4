from __future__ import annotations

from dataclasses import dataclass

from prosperity4bt.domain.datamodel import ConversionObservation, Observation


@dataclass(frozen=True)
class ConversionResult:
    applied: int
    cash_delta: float
    unit_price: float


def apply_conversions(
    product: str,
    requested: int,
    positions: dict[str, int],
    cash_by_product: dict[str, float],
    observations: Observation,
) -> ConversionResult:
    if requested == 0:
        return ConversionResult(applied=0, cash_delta=0.0, unit_price=0.0)

    observation = observations.conversionObservations.get(product)
    if observation is None:
        return ConversionResult(applied=0, cash_delta=0.0, unit_price=0.0)

    positions.setdefault(product, 0)
    cash_by_product.setdefault(product, 0.0)

    if requested > 0:
        unit_price = (
            observation.askPrice + observation.transportFees + observation.importTariff
        )
        cash_delta = -(requested * unit_price)
    else:
        unit_price = (
            observation.bidPrice - observation.transportFees - observation.exportTariff
        )
        cash_delta = abs(requested) * unit_price

    positions[product] += requested
    cash_by_product[product] += cash_delta
    return ConversionResult(applied=requested, cash_delta=cash_delta, unit_price=unit_price)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PriceSnapshot:
    day: int
    timestamp: int
    product: str
    bid_prices: list[int]
    bid_volumes: list[int]
    ask_prices: list[int]
    ask_volumes: list[int]
    mid_price: float
    profit_and_loss: float


def _column_values(columns: list[str], indices: list[int]) -> list[int]:
    values: list[int] = []
    for index in indices:
        value = columns[index]
        if value == "":
            break
        values.append(int(float(value)))
    return values


def load_prices(file: Path) -> list[PriceSnapshot]:
    rows: list[PriceSnapshot] = []
    for line in file.read_text(encoding="utf-8").splitlines()[1:]:
        columns = line.split(";")
        rows.append(
            PriceSnapshot(
                day=int(columns[0]),
                timestamp=int(columns[1]),
                product=columns[2],
                bid_prices=_column_values(columns, [3, 5, 7]),
                bid_volumes=_column_values(columns, [4, 6, 8]),
                ask_prices=_column_values(columns, [9, 11, 13]),
                ask_volumes=_column_values(columns, [10, 12, 14]),
                mid_price=float(columns[15]),
                profit_and_loss=float(columns[16]),
            )
        )
    return rows

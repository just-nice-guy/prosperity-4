from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ObservationSnapshot:
    timestamp: int
    product: str
    bidPrice: float
    askPrice: float
    transportFees: float
    exportTariff: float
    importTariff: float
    sugarPrice: float = 0.0
    sunlightIndex: float = 0.0


def _detect_delimiter(header_line: str) -> str:
    return ";" if header_line.count(";") >= header_line.count(",") else ","


def load_observations(file: Path | None) -> list[ObservationSnapshot]:
    if file is None or not file.exists():
        return []

    text = file.read_text(encoding="utf-8").splitlines()
    if not text:
        return []
    delimiter = _detect_delimiter(text[0])

    reader = csv.DictReader(text, delimiter=delimiter)
    rows: list[ObservationSnapshot] = []
    for row in reader:
        product = row.get("product") or row.get("symbol") or "CONVERSION"
        rows.append(
            ObservationSnapshot(
                timestamp=int(float(row["timestamp"])),
                product=product,
                bidPrice=float(row.get("bidPrice", 0) or 0),
                askPrice=float(row.get("askPrice", 0) or 0),
                transportFees=float(row.get("transportFees", 0) or 0),
                exportTariff=float(row.get("exportTariff", 0) or 0),
                importTariff=float(row.get("importTariff", 0) or 0),
                sugarPrice=float(row.get("sugarPrice", 0) or 0),
                sunlightIndex=float(row.get("sunlightIndex", 0) or 0),
            )
        )
    return rows

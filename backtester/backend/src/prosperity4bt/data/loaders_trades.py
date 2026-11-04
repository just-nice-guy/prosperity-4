from __future__ import annotations

from pathlib import Path

from prosperity4bt.domain.datamodel import Trade


def load_trades(file: Path | None) -> list[Trade]:
    if file is None or not file.exists():
        return []

    rows: list[Trade] = []
    for line in file.read_text(encoding="utf-8").splitlines()[1:]:
        columns = line.split(";")
        rows.append(
            Trade(
                symbol=columns[3],
                price=int(float(columns[5])),
                quantity=int(float(columns[6])),
                buyer=columns[1] or "",
                seller=columns[2] or "",
                timestamp=int(columns[0]),
            )
        )
    return rows

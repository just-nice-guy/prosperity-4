from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from prosperity4bt.core.pnl import apply_fill, mark_to_market
from prosperity4bt.domain.datamodel import Trade


class PnlTests(unittest.TestCase):
    def test_apply_fill_updates_cash_and_position_for_buy(self) -> None:
        positions: dict[str, int] = {}
        cash: dict[str, float] = {}
        apply_fill(
            Trade(symbol="EMERALDS", price=10000, quantity=2, buyer="SUBMISSION", seller="BOOK", timestamp=0),
            positions,
            cash,
        )
        self.assertEqual(positions["EMERALDS"], 2)
        self.assertEqual(cash["EMERALDS"], -20000)

    def test_mark_to_market_uses_mid_price(self) -> None:
        snapshot = mark_to_market(
            positions={"EMERALDS": 2},
            cash_by_product={"EMERALDS": -20000.0},
            mid_prices={"EMERALDS": 10010.0},
        )
        self.assertEqual(snapshot.mark_to_market_by_product["EMERALDS"], 20.0)


if __name__ == "__main__":
    unittest.main()

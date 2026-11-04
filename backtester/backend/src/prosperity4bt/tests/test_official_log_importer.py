from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from prosperity4bt.adapters.official_log_importer import import_official_log


SAMPLE_LOG = """
Sandbox logs:
hello

Activities log:
timestamp;product;profit_and_loss
0;EMERALDS;12

Trade History:
timestamp;symbol;price;quantity
0;EMERALDS;10000;2
"""


class OfficialLogImporterTests(unittest.TestCase):
    def test_imports_sections(self) -> None:
        imported = import_official_log(SAMPLE_LOG)
        self.assertEqual(imported.sandbox_lines, ["hello"])
        self.assertEqual(len(imported.activity_rows), 1)
        self.assertEqual(len(imported.trade_rows), 1)


if __name__ == "__main__":
    unittest.main()

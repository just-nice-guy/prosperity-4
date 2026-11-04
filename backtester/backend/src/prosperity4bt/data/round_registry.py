from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


PRICE_RE = re.compile(r"prices_round_(?P<round>\d+)_day_(?P<day>-?\d+)\.csv$")
TRADE_RE = re.compile(r"trades_round_(?P<round>\d+)_day_(?P<day>-?\d+)\.csv$")
OBS_RE = re.compile(r"observations_round_(?P<round>\d+)_day_(?P<day>-?\d+)\.csv$")


@dataclass(frozen=True)
class RoundDayFiles:
    round_num: int
    day_num: int
    prices_file: Path
    trades_file: Path | None
    observations_file: Path | None


class RoundRegistry:
    def __init__(self, data_roots: list[Path]) -> None:
        self._data_roots = [root for root in data_roots if root.exists()]

    def list_round_days(self) -> list[tuple[int, int]]:
        return sorted({(item.round_num, item.day_num) for item in self._discover()})

    def resolve(self, round_num: int, day_num: int) -> RoundDayFiles:
        for item in self._discover():
            if item.round_num == round_num and item.day_num == day_num:
                return item
        raise FileNotFoundError(f"No data found for round {round_num} day {day_num}")

    def _discover(self) -> list[RoundDayFiles]:
        price_map: dict[tuple[int, int], Path] = {}
        trade_map: dict[tuple[int, int], Path] = {}
        obs_map: dict[tuple[int, int], Path] = {}

        for root in self._data_roots:
            for file in root.rglob("*.csv"):
                name = file.name
                if match := PRICE_RE.match(name):
                    price_map[(int(match["round"]), int(match["day"]))] = file
                elif match := TRADE_RE.match(name):
                    trade_map[(int(match["round"]), int(match["day"]))] = file
                elif match := OBS_RE.match(name):
                    obs_map[(int(match["round"]), int(match["day"]))] = file

        entries: list[RoundDayFiles] = []
        for key, prices_file in price_map.items():
            entries.append(
                RoundDayFiles(
                    round_num=key[0],
                    day_num=key[1],
                    prices_file=prices_file,
                    trades_file=trade_map.get(key),
                    observations_file=obs_map.get(key),
                )
            )
        return sorted(entries, key=lambda item: (item.round_num, item.day_num))

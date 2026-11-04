from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from prosperity4bt.config.settings import get_settings
from prosperity4bt.data.round_registry import RoundDayFiles, RoundRegistry


@dataclass(frozen=True)
class DatasetInfo:
    round_num: int
    day_num: int
    prices_file: str
    trades_file: str | None
    observations_file: str | None


class DatasetCatalog:
    def __init__(self, data_roots: list[Path] | None = None) -> None:
        settings = get_settings()
        self._registry = RoundRegistry(data_roots or list(settings.default_data_roots))

    def list_datasets(self) -> list[DatasetInfo]:
        items: list[DatasetInfo] = []
        for round_num, day_num in self._registry.list_round_days():
            files = self._registry.resolve(round_num, day_num)
            items.append(self._to_info(files))
        return items

    def resolve(self, round_num: int, day_num: int) -> RoundDayFiles:
        return self._registry.resolve(round_num, day_num)

    @staticmethod
    def _to_info(files: RoundDayFiles) -> DatasetInfo:
        return DatasetInfo(
            round_num=files.round_num,
            day_num=files.day_num,
            prices_file=str(files.prices_file),
            trades_file=str(files.trades_file) if files.trades_file else None,
            observations_file=str(files.observations_file) if files.observations_file else None,
        )

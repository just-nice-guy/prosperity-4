from __future__ import annotations

from collections import defaultdict
from typing import Iterable, TypeVar


T = TypeVar("T")


def group_by_timestamp(items: Iterable[T]) -> dict[int, list[T]]:
    grouped: dict[int, list[T]] = defaultdict(list)
    for item in items:
        grouped[getattr(item, "timestamp")].append(item)
    return dict(sorted(grouped.items()))


def sorted_timestamps(*groups: dict[int, object]) -> list[int]:
    values: set[int] = set()
    for group in groups:
        values.update(group.keys())
    return sorted(values)

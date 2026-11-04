from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EventRecord:
    kind: str
    timestamp: int
    round_num: int = 0
    day_num: int = 0
    symbol: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionTraceRecord:
    timestamp: int
    round_num: int = 0
    day_num: int = 0
    symbol: str | None = None
    payload: dict[str, object] = field(default_factory=dict)

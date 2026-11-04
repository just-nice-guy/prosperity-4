from __future__ import annotations

from dataclasses import asdict

from prosperity4bt.logging.event_models import DecisionTraceRecord, EventRecord


class EventLogger:
    def __init__(self) -> None:
        self.events: list[EventRecord] = []
        self.decision_traces: list[DecisionTraceRecord] = []
        self.sandbox_lines: list[str] = []

    def emit(
        self,
        kind: str,
        timestamp: int,
        round_num: int = 0,
        day_num: int = 0,
        symbol: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.events.append(
            EventRecord(
                kind=kind,
                timestamp=timestamp,
                round_num=round_num,
                day_num=day_num,
                symbol=symbol,
                payload=payload or {},
            )
        )

    def decision(
        self,
        timestamp: int,
        round_num: int = 0,
        day_num: int = 0,
        symbol: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.decision_traces.append(
            DecisionTraceRecord(
                timestamp=timestamp,
                round_num=round_num,
                day_num=day_num,
                symbol=symbol,
                payload=payload or {},
            )
        )

    def capture_stdout(self, text: str) -> None:
        if not text:
            return
        self.sandbox_lines.extend(line for line in text.splitlines() if line.strip())

    def event_dicts(self) -> list[dict[str, object]]:
        return [asdict(item) for item in self.events]

    def decision_dicts(self) -> list[dict[str, object]]:
        return [asdict(item) for item in self.decision_traces]

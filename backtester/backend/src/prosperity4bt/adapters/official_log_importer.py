from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportedOfficialLog:
    label: str
    sandbox_lines: list[str]
    activity_rows: list[dict[str, str]]
    trade_rows: list[dict[str, str]]


def import_official_log(text: str, label: str = "official-log") -> ImportedOfficialLog:
    trimmed = text.strip()

    # Try JSON format first (downloaded .log file from Prosperity platform)
    if trimmed.startswith("{"):
        try:
            data = json.loads(trimmed)
            if "activitiesLog" in data or "tradeHistory" in data or "logs" in data:
                return _import_json_format(data, label)
        except json.JSONDecodeError:
            pass

    # Fall back to plain-text section-based format
    return _import_text_format(trimmed, label)


def _import_json_format(data: dict, label: str) -> ImportedOfficialLog:
    activity_rows = _parse_csv_section(data.get("activitiesLog", ""))

    sandbox_lines: list[str] = []
    for entry in data.get("logs", []):
        log_text = entry.get("sandboxLog", "")
        if log_text:
            sandbox_lines.extend(line for line in log_text.splitlines() if line.strip())

    trade_rows: list[dict[str, str]] = []
    for t in data.get("tradeHistory", []):
        buyer = str(t.get("buyer", ""))
        seller = str(t.get("seller", ""))
        # Only include trades involving SUBMISSION (skip market-to-market)
        if buyer != "SUBMISSION" and seller != "SUBMISSION":
            continue
        trade_rows.append({
            "timestamp": str(t.get("timestamp", 0)),
            "buyer": buyer,
            "seller": seller,
            "symbol": str(t.get("symbol", "")),
            "currency": str(t.get("currency", "SEASHELLS")),
            "price": str(t.get("price", 0)),
            "quantity": str(t.get("quantity", 0)),
        })

    return ImportedOfficialLog(
        label=label,
        sandbox_lines=sandbox_lines,
        activity_rows=activity_rows,
        trade_rows=trade_rows,
    )


def _import_text_format(text: str, label: str) -> ImportedOfficialLog:
    sections = _split_sections(text)
    activity_rows = _parse_csv_section(sections.get("Activities log", ""))
    trade_rows = _parse_csv_section(sections.get("Trade History", ""))
    sandbox_lines = [
        line
        for line in sections.get("Sandbox logs", "").splitlines()
        if line.strip()
    ]
    return ImportedOfficialLog(
        label=label,
        sandbox_lines=sandbox_lines,
        activity_rows=activity_rows,
        trade_rows=trade_rows,
    )


def _split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "root"
    sections[current] = []
    for line in text.splitlines():
        stripped = line.strip().rstrip(":")
        if stripped in {"Sandbox logs", "Activities log", "Trade History"}:
            current = stripped
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _parse_csv_section(text: str) -> list[dict[str, str]]:
    cleaned = text.strip()
    if not cleaned:
        return []
    delimiter = ";" if cleaned.splitlines()[0].count(";") >= cleaned.splitlines()[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(cleaned), delimiter=delimiter)
    return [dict(row) for row in reader]

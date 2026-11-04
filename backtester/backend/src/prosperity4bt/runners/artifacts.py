from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from prosperity4bt.core.engine import EngineConfig, EngineResult
from prosperity4bt.logging.exporters import write_json, write_jsonl, write_text


def write_run_artifacts(run_directory: Path, config: EngineConfig, result: EngineResult) -> None:
    run_directory.mkdir(parents=True, exist_ok=True)

    write_json(
        run_directory / "manifest.json",
        {
            "run_id": result.run_id,
            "status": result.status,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "trader_path": config.trader_path,
            "datasets": [asdict(item) for item in config.round_days],
            "matching_mode": config.matching_mode,
        },
    )
    write_json(
        run_directory / "summary.json",
        {
            "run_id": result.run_id,
            "status": result.status,
            "total_ticks": result.total_ticks,
            "total_orders": result.total_orders,
            "total_fills": result.total_fills,
            "final_pnl": result.final_pnl,
            "final_positions": result.final_positions,
            "cash_by_product": result.cash_by_product,
            "mark_to_market_by_product": result.mark_to_market_by_product,
            "dataset_summaries": result.dataset_summaries,
            "config": result.config_snapshot,
        },
    )
    write_jsonl(run_directory / "events.jsonl", result.events)
    write_jsonl(run_directory / "decision_trace.jsonl", result.decision_trace)
    write_text(run_directory / "sandbox.log", result.sandbox_log)
    write_json(
        run_directory / "trades.json",
        {
            "own_trades": result.own_trade_rows,
            "market_trades": result.market_trade_rows,
        },
    )
    _write_activity_csv(run_directory / "activity.csv", result.activity_rows)
    write_json(run_directory / "run_config.json", asdict(config))


def write_failed_run_artifacts(
    run_directory: Path,
    run_id: str,
    trader_path: str,
    message: str,
) -> None:
    run_directory.mkdir(parents=True, exist_ok=True)
    write_json(
        run_directory / "manifest.json",
        {
            "run_id": run_id,
            "status": "failed",
            "trader_path": trader_path,
        },
    )
    write_json(
        run_directory / "summary.json",
        {
            "run_id": run_id,
            "status": "failed",
            "error": message,
        },
    )
    write_text(run_directory / "sandbox.log", message)


def _write_activity_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

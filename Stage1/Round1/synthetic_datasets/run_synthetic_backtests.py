"""Run the trader on each synthetic CSV dataset and save results in
Prosperity log JSON format (so the existing visualizer can render them).

Output: Stage1/Round1/synthetic_datasets/results/<scenario>.log (Prosperity-format JSON)
        Stage1/Round1/synthetic_datasets/results/manifest.json (summary of all runs)

Usage from repo root:
    python Stage1/Round1/synthetic_datasets/run_synthetic_backtests.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import uuid
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backtester" / "backend" / "src"))

from prosperity4bt.adapters.trader_loader import load_trader
from prosperity4bt.core.engine import DayRequest, EngineConfig, run_engine

DEFAULT_TRADER_PATH = str(REPO / "Stage1" / "Round1" / "pepper" / "trader.py")
DATA_DIR = REPO / "Stage1" / "Round1" / "synthetic_datasets" / "data"
RESULTS_BASE = REPO / "Stage1" / "Round1" / "synthetic_datasets" / "results"
RESULTS_BASE.mkdir(parents=True, exist_ok=True)

POS_LIMIT = 80
ROUND_NUM = 99
DAY_NUM = 0


def _activity_csv(activity_rows: list[dict]) -> str:
    """Re-serialize activity rows to the Prosperity activitiesLog CSV string."""
    header = ("day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;"
              "bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;"
              "ask_price_3;ask_volume_3;mid_price;profit_and_loss")
    out = [header]
    for r in activity_rows:
        cols = [
            str(r.get("day", 0)),
            str(r.get("timestamp", 0)),
            str(r.get("product", "")),
            str(r.get("bid_price_1", "") or ""),
            str(r.get("bid_volume_1", "") or ""),
            str(r.get("bid_price_2", "") or ""),
            str(r.get("bid_volume_2", "") or ""),
            str(r.get("bid_price_3", "") or ""),
            str(r.get("bid_volume_3", "") or ""),
            str(r.get("ask_price_1", "") or ""),
            str(r.get("ask_volume_1", "") or ""),
            str(r.get("ask_price_2", "") or ""),
            str(r.get("ask_volume_2", "") or ""),
            str(r.get("ask_price_3", "") or ""),
            str(r.get("ask_volume_3", "") or ""),
            str(r.get("mid_price", 0)),
            str(r.get("pnl", r.get("profit_and_loss", 0))),
        ]
        out.append(";".join(cols))
    return "\n".join(out)


def _trade_history(own: list[dict], bot: list[dict]) -> list[dict]:
    """Combine own + bot trades into the tradeHistory format."""
    history = []
    for src, label_default in [(own, "SUBMISSION"), (bot, None)]:
        for t in src:
            qty = int(t.get("quantity", 0))
            buyer = t.get("buyer") or (label_default if qty > 0 else "")
            seller = t.get("seller") or (label_default if qty < 0 else "")
            history.append({
                "timestamp": int(t.get("timestamp", 0)),
                "buyer": buyer or "",
                "seller": seller or "",
                "symbol": t.get("symbol", ""),
                "currency": "SEASHELLS",
                "price": float(t.get("price", 0)),
                "quantity": abs(qty),
            })
    history.sort(key=lambda x: x["timestamp"])
    return history


# Parse "t=<ts> ..." lines from sandbox_log into per-timestamp lambdaLog entries
TS_RE = re.compile(r"^t=(\d+)\s")


def _logs_from_sandbox(sandbox_log: str) -> list[dict]:
    logs = []
    by_ts: dict[int, list[str]] = {}
    for line in sandbox_log.splitlines():
        m = TS_RE.match(line)
        if m:
            ts = int(m.group(1))
            by_ts.setdefault(ts, []).append(line)
    for ts in sorted(by_ts.keys()):
        logs.append({
            "sandboxLog": "",
            "lambdaLog": "\n".join(by_ts[ts]),
            "timestamp": ts,
        })
    return logs


def run_one(csv_path: Path, trader_path: str, results_dir: Path) -> tuple[Path, dict]:
    """Run trader on one synthetic CSV. Returns (output_path, summary)."""
    stem = csv_path.stem  # prices_round_99_day_0__<scenario>
    scenario = stem.split("__", 1)[1] if "__" in stem else stem

    # Stage canonical-named prices + trades CSVs in a temp dir for engine discovery.
    # Without the trades file, prosperity-mode matching can't fill us passively
    # (it needs the bot trade history to detect "a market trade crossed our quote").
    import shutil, tempfile
    tmp_root = Path(tempfile.mkdtemp(prefix="synth_"))
    canonical_prices = tmp_root / f"prices_round_{ROUND_NUM}_day_{DAY_NUM}.csv"
    shutil.copy(csv_path, canonical_prices)
    trades_src = csv_path.parent / csv_path.name.replace("prices_", "trades_")
    if trades_src.exists():
        canonical_trades = tmp_root / f"trades_round_{ROUND_NUM}_day_{DAY_NUM}.csv"
        shutil.copy(trades_src, canonical_trades)

    config = EngineConfig(
        trader_path=trader_path,
        round_days=[DayRequest(round_num=ROUND_NUM, day_num=DAY_NUM)],
        data_roots=[str(tmp_root)],
        limit_overrides={"INTARIAN_PEPPER_ROOT": POS_LIMIT},
        matching_mode="prosperity",
        time_limit_ms=900,
    )
    trader = load_trader(trader_path)
    result = run_engine(config=config, trader=trader)
    shutil.rmtree(tmp_root, ignore_errors=True)

    activities_csv = _activity_csv(result.activity_rows)
    trade_history = _trade_history(result.own_trade_rows, result.market_trade_rows)
    logs = _logs_from_sandbox(result.sandbox_log)

    payload = {
        "submissionId": uuid.uuid4().hex,
        "scenario": scenario,
        "activitiesLog": activities_csv,
        "logs": logs,
        "tradeHistory": trade_history,
    }
    out_path = results_dir / f"{scenario}.log"
    out_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = {
        "scenario": scenario,
        "file": out_path.name,
        "pnl": result.final_pnl,
        "fills": result.total_fills,
        "orders": result.total_orders,
        "ticks": result.total_ticks,
        "final_pos": result.final_positions.get("INTARIAN_PEPPER_ROOT", 0),
        "n_own_trades": len(result.own_trade_rows),
        "n_bot_trades": len(result.market_trade_rows),
    }
    return out_path, summary


def run_all(trader_path: str, label: str | None = None) -> dict:
    """Run all synthetic datasets through the given trader. Returns manifest dict.

    Results are stored under results/<label>/ so multiple trader versions can
    coexist. Label defaults to the trader file's stem.
    """
    trader_p = Path(trader_path).resolve()
    if not trader_p.exists():
        raise FileNotFoundError(f"Trader not found: {trader_p}")
    if label is None:
        label = trader_p.stem
    results_dir = RESULTS_BASE / label
    results_dir.mkdir(parents=True, exist_ok=True)

    csvs = sorted(DATA_DIR.glob("prices_round_99_day_0__*.csv"))
    print(f"Trader: {trader_p}  →  results/{label}/")
    print(f"Found {len(csvs)} synthetic datasets")

    summaries = []
    for csv_path in csvs:
        out_path, summary = run_one(csv_path, str(trader_p), results_dir)
        s = summary
        print(f"  {s['scenario']:25s}  PnL={s['pnl']:>+8.0f}  fills={s['fills']:>4d}  pos={s['final_pos']:>+3d}  → {out_path.name}")
        summaries.append(summary)

    manifest = {
        "trader_label": label,
        "trader_path": str(trader_p),
        "datasets": summaries,
    }
    (results_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest written: {results_dir / 'manifest.json'}")
    return manifest


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--trader", default=DEFAULT_TRADER_PATH,
                        help="Path to trader .py file (default: Stage1/Round1/pepper/trader.py)")
    parser.add_argument("--label", default=None,
                        help="Subdir name under results/ (default: trader file stem)")
    args = parser.parse_args()
    run_all(args.trader, args.label)


if __name__ == "__main__":
    main()

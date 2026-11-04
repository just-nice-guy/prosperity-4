from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from prosperity4bt.adapters.trader_loader import load_trader
from prosperity4bt.core.engine import engine_config_from_dict, run_engine
from prosperity4bt.runners.artifacts import write_failed_run_artifacts, write_run_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local Prosperity 4 backtest worker.")
    parser.add_argument("--config", required=True, help="Path to the JSON worker config.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    run_directory = Path(payload["run_directory"]).resolve()
    run_id = str(payload["run_id"])
    trader_path = str(payload["trader_path"])

    try:
        config = engine_config_from_dict(payload)
        trader = load_trader(trader_path)
        result = run_engine(config=config, trader=trader)
        write_run_artifacts(run_directory=run_directory, config=config, result=result)
    except Exception:
        write_failed_run_artifacts(
            run_directory=run_directory,
            run_id=run_id,
            trader_path=trader_path,
            message=traceback.format_exc(),
        )
        raise


if __name__ == "__main__":
    main()

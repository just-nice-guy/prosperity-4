from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path


def load_trader(trader_path: str | Path):
    trader_file = Path(trader_path).resolve()
    if not trader_file.exists():
        raise FileNotFoundError(f"Trader file not found: {trader_file}")

    module_name = f"prosperity4bt_user_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, trader_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load trader module from {trader_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # required for @dataclass to resolve its module
    spec.loader.exec_module(module)

    trader_cls = getattr(module, "Trader", None)
    if trader_cls is None:
        raise AttributeError(f"No Trader class found in {trader_file}")
    return trader_cls()

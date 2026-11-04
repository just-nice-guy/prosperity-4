from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from prosperity4bt.data.catalog import DatasetCatalog
from prosperity4bt.data.loaders_prices import load_prices
from prosperity4bt.data.loaders_trades import load_trades
from prosperity4bt.data.round_registry import RoundDayFiles


router = APIRouter(prefix="/api", tags=["data"])


@router.get("/datasets")
def list_datasets() -> list[dict[str, object]]:
    catalog = DatasetCatalog()
    return [item.__dict__ for item in catalog.list_datasets()]


@router.get("/datasets/products")
def list_products() -> list[str]:
    """Return distinct product names found across all datasets."""
    catalog = DatasetCatalog()
    datasets = catalog.list_datasets()
    products: set[str] = set()
    for ds in datasets:
        try:
            files: RoundDayFiles = catalog.resolve(ds.round_num, ds.day_num)
        except Exception:
            continue
        for snap in load_prices(files.prices_file):
            products.add(snap.product)
    return sorted(products)


@router.get("/datasets/prices")
def get_raw_prices(product: str = Query(...)) -> list[dict[str, object]]:
    """Return best bid/ask price snapshots for a product across all datasets."""
    catalog = DatasetCatalog()
    datasets = catalog.list_datasets()
    rows: list[dict[str, object]] = []
    for ds in datasets:
        try:
            files: RoundDayFiles = catalog.resolve(ds.round_num, ds.day_num)
        except Exception:
            continue
        snapshots = load_prices(files.prices_file)
        for snap in snapshots:
            if snap.product != product:
                continue
            rows.append(
                {
                    "round_num": ds.round_num,
                    "day_num": ds.day_num,
                    "timestamp": snap.timestamp,
                    "best_bid": snap.bid_prices[0] if snap.bid_prices else None,
                    "best_ask": snap.ask_prices[0] if snap.ask_prices else None,
                    "mid_price": snap.mid_price,
                }
            )
    return rows


@router.get("/datasets/orderbook")
def get_dataset_orderbook(
    product: str = Query(...),
    round_num: int | None = Query(None),
    day_num: int | None = Query(None),
    timestamp: int | None = Query(None),
) -> dict[str, object]:
    """Return one full order book snapshot from the raw market data."""
    catalog = DatasetCatalog()
    datasets = catalog.list_datasets()

    if round_num is not None:
        datasets = [ds for ds in datasets if ds.round_num == round_num]
    if day_num is not None:
        datasets = [ds for ds in datasets if ds.day_num == day_num]

    for ds in datasets:
        try:
            files: RoundDayFiles = catalog.resolve(ds.round_num, ds.day_num)
        except Exception:
            continue
        for snap in load_prices(files.prices_file):
            if snap.product != product:
                continue
            if timestamp is not None and snap.timestamp != timestamp:
                continue
            return {
                "round_num": ds.round_num,
                "day_num": ds.day_num,
                "timestamp": snap.timestamp,
                "product": snap.product,
                "bid_prices": snap.bid_prices,
                "bid_volumes": snap.bid_volumes,
                "ask_prices": snap.ask_prices,
                "ask_volumes": snap.ask_volumes,
                "mid_price": snap.mid_price,
            }

    raise HTTPException(status_code=404, detail="Order book snapshot not found")


@router.get("/datasets/trades")
def get_raw_trades(product: str = Query(...)) -> list[dict[str, object]]:
    """Return market trades for a product across all datasets."""
    catalog = DatasetCatalog()
    datasets = catalog.list_datasets()
    rows: list[dict[str, object]] = []
    for ds in datasets:
        try:
            files: RoundDayFiles = catalog.resolve(ds.round_num, ds.day_num)
        except Exception:
            continue
        trades = load_trades(files.trades_file)
        for t in trades:
            if t.symbol != product:
                continue
            rows.append(
                {
                    "round_num": ds.round_num,
                    "day_num": ds.day_num,
                    "timestamp": t.timestamp,
                    "price": t.price,
                    "quantity": abs(t.quantity),
                }
            )
    return rows

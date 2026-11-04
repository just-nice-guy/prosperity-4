from __future__ import annotations

from typing import Optional
import re
import numpy as np
import pandas as pd


TOL = 1e-12


# =============================================================================
# 0. Conversion OrderDepth -> DataFrame d'arbitrage
# =============================================================================

def orderbook_to_arbitrage_dataframe(
    order_depths: dict,
    spot_symbol: str = "VELVETFRUIT_EXTRACT",
    option_prefix: str = "VEV_",
    ignore_unknown_products: bool = True,
) -> pd.DataFrame:
    """
    Convertit un dictionnaire de carnets d'ordres en DataFrame compatible
    avec les fonctions d'arbitrage.

    Format d'entrée attendu:
        {
            "VEV_5000": OrderDepth(
                buy_orders={249: 25},
                sell_orders={255: -9, 256: -16}
            ),
            "VELVETFRUIT_EXTRACT": OrderDepth(
                buy_orders={5242: 57},
                sell_orders={5247: -16, 5248: -41}
            )
        }

    Convention du DataFrame de sortie:
        product     : "SPOT" ou "OPTION"
        strike      : strike du call, NaN pour le spot
        buy_price   : prix auquel on peut acheter, donc meilleur ask
        sell_price  : prix auquel on peut vendre, donc meilleur bid
        buy_qty     : quantité disponible au meilleur ask
        sell_qty    : quantité disponible au meilleur bid
        symbol      : symbole original

    Important:
        buy_orders dans le carnet = ordres d'achat des autres participants.
        Donc c'est le prix auquel toi tu peux vendre.

        sell_orders dans le carnet = ordres de vente des autres participants.
        Donc c'est le prix auquel toi tu peux acheter.
    """
    rows = []

    option_regex = re.compile(rf"^{re.escape(option_prefix)}(\d+(?:\.\d+)?)$")

    for symbol, depth in order_depths.items():

        if isinstance(depth, dict):
            buy_orders = depth.get("buy_orders", {}) or {}
            sell_orders = depth.get("sell_orders", {}) or {}
        else:
            buy_orders = getattr(depth, "buy_orders", {}) or {}
            sell_orders = getattr(depth, "sell_orders", {}) or {}

        best_bid = max(buy_orders.keys()) if buy_orders else np.nan
        best_ask = min(sell_orders.keys()) if sell_orders else np.nan

        best_bid_qty = abs(buy_orders[best_bid]) if buy_orders else np.nan
        best_ask_qty = abs(sell_orders[best_ask]) if sell_orders else np.nan

        if symbol == spot_symbol:
            product = "SPOT"
            strike = np.nan

        else:
            match = option_regex.match(symbol)

            if match:
                product = "OPTION"
                strike = float(match.group(1))

            else:
                if ignore_unknown_products:
                    continue

                raise ValueError(
                    f"Produit inconnu: {symbol}. "
                    f"Ce symbole n'est ni le spot '{spot_symbol}', "
                    f"ni une option avec préfixe '{option_prefix}'."
                )

        rows.append(
            {
                "product": product,
                "strike": strike,
                "buy_price": float(best_ask) if not pd.isna(best_ask) else np.nan,
                "sell_price": float(best_bid) if not pd.isna(best_bid) else np.nan,
                "buy_qty": float(best_ask_qty) if not pd.isna(best_ask_qty) else np.nan,
                "sell_qty": float(best_bid_qty) if not pd.isna(best_bid_qty) else np.nan,
                "symbol": symbol,
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "product",
                "strike",
                "buy_price",
                "sell_price",
                "buy_qty",
                "sell_qty",
                "symbol",
            ]
        )

    df["_sort_product"] = df["product"].map({"SPOT": 0, "OPTION": 1})
    df["_sort_strike"] = df["strike"].fillna(-np.inf)

    df = (
        df.sort_values(["_sort_product", "_sort_strike"])
          .drop(columns=["_sort_product", "_sort_strike"])
          .reset_index(drop=True)
    )

    return df


# =============================================================================
# 1. Normalisation du DataFrame de marché
# =============================================================================

def _norm_market(df: pd.DataFrame) -> pd.DataFrame:
    """
    Colonnes obligatoires:
        product, strike, buy_price, sell_price

    Colonnes optionnelles:
        buy_qty, sell_qty, symbol

    Convention:
        buy_price  = ask = prix payé pour acheter
        sell_price = bid = prix reçu pour vendre
    """
    required = {"product", "strike", "buy_price", "sell_price"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Colonnes manquantes: {sorted(missing)}")

    out = df.copy()

    out["product"] = out["product"].astype(str).str.upper().str.strip()
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["buy_price"] = pd.to_numeric(out["buy_price"], errors="coerce")
    out["sell_price"] = pd.to_numeric(out["sell_price"], errors="coerce")

    if "buy_qty" not in out.columns:
        out["buy_qty"] = np.nan
    else:
        out["buy_qty"] = pd.to_numeric(out["buy_qty"], errors="coerce")

    if "sell_qty" not in out.columns:
        out["sell_qty"] = np.nan
    else:
        out["sell_qty"] = pd.to_numeric(out["sell_qty"], errors="coerce")

    if "symbol" not in out.columns:
        out["symbol"] = None

    valid_products = {"SPOT", "OPTION"}

    if not out["product"].isin(valid_products).all():
        raise ValueError("La colonne product doit contenir uniquement 'SPOT' ou 'OPTION'.")

    out.loc[out["product"] == "SPOT", "strike"] = np.nan
    out["_row_id"] = out.index

    return out


def _valid_options(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["product"] == "OPTION") & df["strike"].notna()].copy()


def _spots(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["product"] == "SPOT"].copy()


def _has_buy(row: pd.Series) -> bool:
    return pd.notna(row["buy_price"])


def _has_sell(row: pd.Series) -> bool:
    return pd.notna(row["sell_price"])


def _available_qty(row: pd.Series, action: str) -> Optional[float]:
    """
    Quantité disponible au meilleur prix.

    BUY:
        on tape le meilleur ask, donc disponibilité = buy_qty

    SELL:
        on tape le meilleur bid, donc disponibilité = sell_qty

    Si la colonne n'est pas renseignée, retourne None.
    """
    if action == "BUY":
        qty = row.get("buy_qty", np.nan)
    elif action == "SELL":
        qty = row.get("sell_qty", np.nan)
    else:
        return None

    if pd.isna(qty):
        return None

    qty = float(qty)

    if qty < 0:
        raise ValueError("Les quantités disponibles doivent être positives.")

    return qty


def _leg(row: pd.Series, action: str, qty: float) -> dict:
    if qty <= 0:
        raise ValueError("La quantité doit être strictement positive.")

    if action == "BUY":
        if pd.isna(row["buy_price"]):
            raise ValueError("Impossible d'acheter: buy_price est NaN.")

        price = float(row["buy_price"])
        cashflow = -qty * price

    elif action == "SELL":
        if pd.isna(row["sell_price"]):
            raise ValueError("Impossible de vendre: sell_price est NaN.")

        price = float(row["sell_price"])
        cashflow = qty * price

    else:
        raise ValueError("action doit valoir 'BUY' ou 'SELL'.")

    return {
        "action": action,
        "row_id": row["_row_id"],
        "symbol": row.get("symbol", None),
        "product": row["product"],
        "strike": None if pd.isna(row["strike"]) else float(row["strike"]),
        "qty": float(qty),
        "price": float(price),
        "cashflow_t0": float(cashflow),
    }


def _cash_deposit(amount: float) -> dict:
    if amount < 0:
        raise ValueError("amount doit être positif ou nul.")

    return {
        "action": "CASH_DEPOSIT",
        "row_id": None,
        "symbol": None,
        "product": "CASH",
        "strike": None,
        "qty": float(amount),
        "price": 1.0,
        "cashflow_t0": -float(amount),
    }


def _cash_borrow(amount: float) -> dict:
    if amount < 0:
        raise ValueError("amount doit être positif ou nul.")

    return {
        "action": "CASH_BORROW",
        "row_id": None,
        "symbol": None,
        "product": "CASH",
        "strike": None,
        "qty": float(amount),
        "price": 1.0,
        "cashflow_t0": float(amount),
    }


def _max_base_qty(
    leg_specs: list[dict],
    default_base_qty: float = 1.0,
) -> float:
    """
    Calcule la taille maximale exploitable à partir des quantités disponibles.

    Chaque leg_spec contient:
        row
        action
        ratio

    Exemple:
        butterfly:
            BUY K1 avec ratio lambda
            SELL K2 avec ratio 1
            BUY K3 avec ratio 1-lambda

        La taille maximale q vérifie:
            lambda*q <= qty disponible K1
            1*q      <= qty disponible K2
            (1-lambda)*q <= qty disponible K3
    """
    limits = []

    for spec in leg_specs:
        row = spec.get("row")
        action = spec.get("action")
        ratio = float(spec.get("ratio", 1.0))

        if row is None:
            continue

        if ratio <= 0:
            continue

        available = _available_qty(row, action)

        if available is not None:
            limits.append(available / ratio)

    if not limits:
        return float(default_base_qty)

    return float(min(limits))


def _make_arbitrage(
    kind: str,
    condition: str,
    violation_per_unit: float,
    leg_specs: list[dict],
    cash_specs: Optional[list[dict]] = None,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
    default_base_qty: float = 1.0,
) -> Optional[dict]:
    """
    Construit un arbitrage avec taille ajustée aux quantités disponibles.

    leg_specs:
        [
            {"row": row, "action": "BUY", "ratio": 1.0},
            {"row": row, "action": "SELL", "ratio": 1.0},
        ]

    cash_specs:
        [
            {"action": "CASH_DEPOSIT", "amount_per_unit": K}
        ]
    """
    if violation_per_unit <= tol:
        return None

    if scale_to_liquidity:
        base_qty = _max_base_qty(leg_specs, default_base_qty=default_base_qty)
    else:
        base_qty = float(default_base_qty)

    if base_qty <= tol:
        return None

    legs = []

    for spec in leg_specs:
        row = spec["row"]
        action = spec["action"]
        ratio = float(spec.get("ratio", 1.0))

        qty = ratio * base_qty

        if qty > tol:
            legs.append(_leg(row, action, qty))

    if cash_specs:
        for spec in cash_specs:
            action = spec["action"]
            amount = float(spec["amount_per_unit"]) * base_qty

            if amount <= tol:
                continue

            if action == "CASH_DEPOSIT":
                legs.append(_cash_deposit(amount))

            elif action == "CASH_BORROW":
                legs.append(_cash_borrow(amount))

            else:
                raise ValueError(f"Action cash inconnue: {action}")

    legs_df = pd.DataFrame(legs)

    return {
        "arbitrage": kind,
        "condition": condition,
        "violation_per_unit": float(violation_per_unit),
        "base_qty": float(base_qty),
        "violation": float(violation_per_unit * base_qty),
        "initial_cashflow": float(legs_df["cashflow_t0"].sum()),
        "legs": legs_df,
    }


# =============================================================================
# 2. Détecteurs explicites d'arbitrage
# =============================================================================

def detect_same_payoff_crossed_quotes(
    df: pd.DataFrame,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
) -> list[dict]:
    """
    Même payoff, prix croisés.

    Condition:
        max(sell_price) <= min(buy_price)

    Si violation:
        acheter la quote la moins chère
        vendre la quote la plus chère
    """
    m = _norm_market(df)

    m = m[
        (m["product"] == "SPOT")
        | ((m["product"] == "OPTION") & m["strike"].notna())
    ].copy()

    m["_strike_key"] = m["strike"].astype(object)
    m.loc[m["product"] == "SPOT", "_strike_key"] = "__SPOT__"

    arbs = []

    for _, g in m.groupby(["product", "_strike_key"], dropna=False):
        buyers = g[g["buy_price"].notna()]
        sellers = g[g["sell_price"].notna()]

        if buyers.empty or sellers.empty:
            continue

        buy_row = buyers.loc[buyers["buy_price"].idxmin()]
        sell_row = sellers.loc[sellers["sell_price"].idxmax()]

        violation = float(sell_row["sell_price"] - buy_row["buy_price"])

        arb = _make_arbitrage(
            kind="same_payoff_crossed_quotes",
            condition="Pour un même payoff, il faut max(sell_price) <= min(buy_price).",
            violation_per_unit=violation,
            leg_specs=[
                {"row": buy_row, "action": "BUY", "ratio": 1.0},
                {"row": sell_row, "action": "SELL", "ratio": 1.0},
            ],
            tol=tol,
            scale_to_liquidity=scale_to_liquidity,
        )

        if arb is not None:
            arbs.append(arb)

    return arbs


def detect_negative_buy_price(
    df: pd.DataFrame,
    tol: float = TOL,
    include_spot: bool = True,
    scale_to_liquidity: bool = True,
) -> list[dict]:
    """
    Prix d'achat négatif.

    Condition:
        buy_price >= 0

    Si violation:
        acheter l'instrument.
    """
    m = _norm_market(df)

    if not include_spot:
        m = m[m["product"] != "SPOT"]

    arbs = []

    for _, row in m.iterrows():
        if not _has_buy(row):
            continue

        violation = -float(row["buy_price"])

        arb = _make_arbitrage(
            kind="negative_buy_price",
            condition="Un payoff terminal non négatif ne doit pas avoir un prix d'achat négatif.",
            violation_per_unit=violation,
            leg_specs=[
                {"row": row, "action": "BUY", "ratio": 1.0},
            ],
            tol=tol,
            scale_to_liquidity=scale_to_liquidity,
        )

        if arb is not None:
            arbs.append(arb)

    return arbs


def detect_call_upper_bound_by_spot(
    df: pd.DataFrame,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
) -> list[dict]:
    """
    Call trop cher par rapport au spot.

    Condition exécutable:
        call_sell_price(K) <= spot_buy_price

    Si violation:
        vendre le call
        acheter le spot
    """
    m = _norm_market(df)
    opts = _valid_options(m)
    spots = _spots(m)

    arbs = []

    for _, opt in opts.iterrows():
        if not _has_sell(opt):
            continue

        for _, spot in spots.iterrows():
            if not _has_buy(spot):
                continue

            violation = float(opt["sell_price"] - spot["buy_price"])

            arb = _make_arbitrage(
                kind="call_upper_bound_by_spot",
                condition="Pour tout K, il faut call_sell_price(K) <= spot_buy_price.",
                violation_per_unit=violation,
                leg_specs=[
                    {"row": opt, "action": "SELL", "ratio": 1.0},
                    {"row": spot, "action": "BUY", "ratio": 1.0},
                ],
                tol=tol,
                scale_to_liquidity=scale_to_liquidity,
            )

            if arb is not None:
                arbs.append(arb)

    return arbs


def detect_call_intrinsic_lower_bound(
    df: pd.DataFrame,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
) -> list[dict]:
    """
    Call trop peu cher par rapport à l'intrinsèque.

    Condition exécutable:
        call_buy_price(K) >= spot_sell_price - K

    Si violation:
        acheter le call
        vendre le spot
        déposer K en cash
    """
    m = _norm_market(df)
    opts = _valid_options(m)
    spots = _spots(m)

    arbs = []

    for _, opt in opts.iterrows():
        if not _has_buy(opt):
            continue

        K = float(opt["strike"])

        for _, spot in spots.iterrows():
            if not _has_sell(spot):
                continue

            violation = float(spot["sell_price"] - K - opt["buy_price"])

            arb = _make_arbitrage(
                kind="call_intrinsic_lower_bound",
                condition="Pour tout K, il faut call_buy_price(K) >= spot_sell_price - K.",
                violation_per_unit=violation,
                leg_specs=[
                    {"row": opt, "action": "BUY", "ratio": 1.0},
                    {"row": spot, "action": "SELL", "ratio": 1.0},
                ],
                cash_specs=[
                    {"action": "CASH_DEPOSIT", "amount_per_unit": K},
                ],
                tol=tol,
                scale_to_liquidity=scale_to_liquidity,
            )

            if arb is not None:
                arbs.append(arb)

    return arbs


def detect_monotonicity_vertical_spread(
    df: pd.DataFrame,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
) -> list[dict]:
    """
    Monotonie en strike / vertical spread positif.

    Condition:
        si K1 < K2:
            call_sell_price(K2) <= call_buy_price(K1)

    Si violation:
        acheter call K1
        vendre call K2
    """
    m = _norm_market(df)
    opts = _valid_options(m)

    arbs = []

    for _, low in opts.iterrows():
        if not _has_buy(low):
            continue

        K1 = float(low["strike"])

        for _, high in opts.iterrows():
            if not _has_sell(high):
                continue

            K2 = float(high["strike"])

            if not K1 < K2:
                continue

            violation = float(high["sell_price"] - low["buy_price"])

            arb = _make_arbitrage(
                kind="monotonicity_vertical_spread",
                condition="Si K1<K2, il faut call_sell_price(K2) <= call_buy_price(K1).",
                violation_per_unit=violation,
                leg_specs=[
                    {"row": low, "action": "BUY", "ratio": 1.0},
                    {"row": high, "action": "SELL", "ratio": 1.0},
                ],
                tol=tol,
                scale_to_liquidity=scale_to_liquidity,
            )

            if arb is not None:
                arbs.append(arb)

    return arbs


def detect_vertical_spread_upper_bound(
    df: pd.DataFrame,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
) -> list[dict]:
    """
    Vertical spread trop cher.

    Condition:
        si K1 < K2:
            call_sell_price(K1) - call_buy_price(K2) <= K2 - K1

    Si violation:
        vendre call K1
        acheter call K2
        déposer K2-K1 en cash
    """
    m = _norm_market(df)
    opts = _valid_options(m)

    arbs = []

    for _, low in opts.iterrows():
        if not _has_sell(low):
            continue

        K1 = float(low["strike"])

        for _, high in opts.iterrows():
            if not _has_buy(high):
                continue

            K2 = float(high["strike"])

            if not K1 < K2:
                continue

            width = K2 - K1
            violation = float(low["sell_price"] - high["buy_price"] - width)

            arb = _make_arbitrage(
                kind="vertical_spread_upper_bound",
                condition="Si K1<K2, il faut call_sell_price(K1)-call_buy_price(K2) <= K2-K1.",
                violation_per_unit=violation,
                leg_specs=[
                    {"row": low, "action": "SELL", "ratio": 1.0},
                    {"row": high, "action": "BUY", "ratio": 1.0},
                ],
                cash_specs=[
                    {"action": "CASH_DEPOSIT", "amount_per_unit": width},
                ],
                tol=tol,
                scale_to_liquidity=scale_to_liquidity,
            )

            if arb is not None:
                arbs.append(arb)

    return arbs


def detect_convexity_butterfly(
    df: pd.DataFrame,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
) -> list[dict]:
    """
    Convexité en strike / butterfly.

    Pour K1 < K2 < K3:
        lambda = (K3-K2)/(K3-K1)

    Condition:
        call_sell_price(K2)
            <= lambda * call_buy_price(K1)
             + (1-lambda) * call_buy_price(K3)

    Si violation:
        acheter lambda calls K1
        vendre 1 call K2
        acheter 1-lambda calls K3
    """
    m = _norm_market(df)
    opts = _valid_options(m)

    arbs = []

    for _, left in opts.iterrows():
        if not _has_buy(left):
            continue

        K1 = float(left["strike"])

        for _, mid in opts.iterrows():
            if not _has_sell(mid):
                continue

            K2 = float(mid["strike"])

            for _, right in opts.iterrows():
                if not _has_buy(right):
                    continue

                K3 = float(right["strike"])

                if not (K1 < K2 < K3):
                    continue

                lam = (K3 - K2) / (K3 - K1)

                cost_wings = (
                    lam * float(left["buy_price"])
                    + (1.0 - lam) * float(right["buy_price"])
                )

                violation = float(mid["sell_price"] - cost_wings)

                arb = _make_arbitrage(
                    kind="convexity_butterfly",
                    condition="Pour K1<K2<K3, il faut C_sell(K2) <= lambda*C_buy(K1)+(1-lambda)*C_buy(K3).",
                    violation_per_unit=violation,
                    leg_specs=[
                        {"row": left, "action": "BUY", "ratio": lam},
                        {"row": mid, "action": "SELL", "ratio": 1.0},
                        {"row": right, "action": "BUY", "ratio": 1.0 - lam},
                    ],
                    tol=tol,
                    scale_to_liquidity=scale_to_liquidity,
                )

                if arb is not None:
                    arbs.append(arb)

    return arbs


def detect_zero_strike_call_spot_equivalence(
    df: pd.DataFrame,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
) -> list[dict]:
    """
    Cas redondant mais utile:
        call de strike 0 contre spot.

    Sous hypothèse S_T >= 0:
        C(K=0) réplique exactement le spot.
    """
    m = _norm_market(df)
    opts = _valid_options(m)
    opts0 = opts[np.isclose(opts["strike"], 0.0)]
    spots = _spots(m)

    arbs = []

    for _, opt in opts0.iterrows():
        for _, spot in spots.iterrows():

            if _has_sell(opt) and _has_buy(spot):
                violation = float(opt["sell_price"] - spot["buy_price"])

                arb = _make_arbitrage(
                    kind="zero_strike_call_too_expensive",
                    condition="Pour K=0, il faut call_sell_price(0) <= spot_buy_price.",
                    violation_per_unit=violation,
                    leg_specs=[
                        {"row": opt, "action": "SELL", "ratio": 1.0},
                        {"row": spot, "action": "BUY", "ratio": 1.0},
                    ],
                    tol=tol,
                    scale_to_liquidity=scale_to_liquidity,
                )

                if arb is not None:
                    arbs.append(arb)

            if _has_buy(opt) and _has_sell(spot):
                violation = float(spot["sell_price"] - opt["buy_price"])

                arb = _make_arbitrage(
                    kind="zero_strike_call_too_cheap",
                    condition="Pour K=0, il faut spot_sell_price <= call_buy_price(0).",
                    violation_per_unit=violation,
                    leg_specs=[
                        {"row": opt, "action": "BUY", "ratio": 1.0},
                        {"row": spot, "action": "SELL", "ratio": 1.0},
                    ],
                    tol=tol,
                    scale_to_liquidity=scale_to_liquidity,
                )

                if arb is not None:
                    arbs.append(arb)

    return arbs


# =============================================================================
# 3. Détection globale des arbitrages explicites
# =============================================================================

def detect_all_explicit_arbitrages(
    df: pd.DataFrame,
    tol: float = TOL,
    scale_to_liquidity: bool = True,
    include_redundant_zero_strike_check: bool = False,
    include_spot_negative_price_check: bool = True,
) -> list[dict]:
    """
    Lance tous les détecteurs explicites non redondants.

    Arbitrages détectés:
        1. même payoff avec prix croisés
        2. prix d'achat négatif
        3. call trop cher par rapport au spot
        4. call trop peu cher par rapport à l'intrinsèque
        5. monotonie / vertical spread positif
        6. vertical spread trop cher
        7. convexité / butterfly

    Le test K=0 contre spot est redondant et désactivé par défaut.
    """
    arbs = []

    arbs.extend(
        detect_same_payoff_crossed_quotes(
            df,
            tol=tol,
            scale_to_liquidity=scale_to_liquidity,
        )
    )

    arbs.extend(
        detect_negative_buy_price(
            df,
            tol=tol,
            include_spot=include_spot_negative_price_check,
            scale_to_liquidity=scale_to_liquidity,
        )
    )

    arbs.extend(
        detect_call_upper_bound_by_spot(
            df,
            tol=tol,
            scale_to_liquidity=scale_to_liquidity,
        )
    )

    arbs.extend(
        detect_call_intrinsic_lower_bound(
            df,
            tol=tol,
            scale_to_liquidity=scale_to_liquidity,
        )
    )

    arbs.extend(
        detect_monotonicity_vertical_spread(
            df,
            tol=tol,
            scale_to_liquidity=scale_to_liquidity,
        )
    )

    arbs.extend(
        detect_vertical_spread_upper_bound(
            df,
            tol=tol,
            scale_to_liquidity=scale_to_liquidity,
        )
    )

    arbs.extend(
        detect_convexity_butterfly(
            df,
            tol=tol,
            scale_to_liquidity=scale_to_liquidity,
        )
    )

    if include_redundant_zero_strike_check:
        arbs.extend(
            detect_zero_strike_call_spot_equivalence(
                df,
                tol=tol,
                scale_to_liquidity=scale_to_liquidity,
            )
        )

    return arbs


# =============================================================================
# 4. Fonctions de sortie
# =============================================================================

def arbitrages_to_dataframe(arbs: list[dict]) -> pd.DataFrame:
    """
    Résumé tabulaire des arbitrages.
    """
    rows = []

    for i, arb in enumerate(arbs):
        rows.append(
            {
                "arb_id": i,
                "arbitrage": arb["arbitrage"],
                "violation_per_unit": arb["violation_per_unit"],
                "base_qty": arb["base_qty"],
                "violation": arb["violation"],
                "initial_cashflow": arb["initial_cashflow"],
                "n_legs": len(arb["legs"]),
                "condition": arb["condition"],
            }
        )

    return pd.DataFrame(rows)


def arbitrage_legs_to_dataframe(arbs: list[dict]) -> pd.DataFrame:
    """
    Retourne toutes les jambes de tous les arbitrages dans un seul DataFrame.
    """
    rows = []

    for i, arb in enumerate(arbs):
        legs = arb["legs"].copy()
        legs.insert(0, "arb_id", i)
        legs.insert(1, "arbitrage", arb["arbitrage"])
        rows.append(legs)

    if not rows:
        return pd.DataFrame(
            columns=[
                "arb_id",
                "arbitrage",
                "action",
                "row_id",
                "symbol",
                "product",
                "strike",
                "qty",
                "price",
                "cashflow_t0",
            ]
        )

    return pd.concat(rows, ignore_index=True)


# =============================================================================
# 5. Payoff terminal
# =============================================================================

def payoff_of_legs(legs: pd.DataFrame, s: float) -> float:
    """
    Calcule le payoff terminal d'un arbitrage pour un niveau donné S_T=s.
    """
    total = 0.0

    for _, leg in legs.iterrows():
        action = leg["action"]
        product = leg["product"]
        qty = float(leg["qty"])

        if product == "CASH":
            if action == "CASH_DEPOSIT":
                total += qty

            elif action == "CASH_BORROW":
                total -= qty

            else:
                raise ValueError(f"Action cash inconnue: {action}")

            continue

        if product == "SPOT":
            payoff = float(s)

        elif product == "OPTION":
            payoff = max(float(s) - float(leg["strike"]), 0.0)

        else:
            raise ValueError(f"Produit inconnu: {product}")

        if action == "BUY":
            total += qty * payoff

        elif action == "SELL":
            total -= qty * payoff

        else:
            raise ValueError(f"Action inconnue: {action}")

    return float(total)


def payoff_table_for_arbitrage(
    arb: dict,
    s_values: list[float] | np.ndarray,
) -> pd.DataFrame:
    """
    Table de payoff terminal pour un arbitrage donné.
    """
    return pd.DataFrame(
        [
            {
                "S_T": float(s),
                "payoff_T": payoff_of_legs(arb["legs"], float(s)),
            }
            for s in s_values
        ]
    )


# =============================================================================
# 6. Pipeline complet
# =============================================================================

def find_arbitrages_from_orderbook(
    order_depths: dict,
    spot_symbol: str = "VELVETFRUIT_EXTRACT",
    option_prefix: str = "VEV_",
    tol: float = TOL,
    scale_to_liquidity: bool = True,
) -> tuple[pd.DataFrame, list[dict], pd.DataFrame, pd.DataFrame]:
    """
    Pipeline complet:
        orderbook -> market_df -> arbitrages -> summary -> legs

    Retourne:
        market_df
        arbs
        summary_df
        legs_df
    """
    market_df = orderbook_to_arbitrage_dataframe(
        order_depths=order_depths,
        spot_symbol=spot_symbol,
        option_prefix=option_prefix,
        ignore_unknown_products=True,
    )

    arbs = detect_all_explicit_arbitrages(
        market_df,
        tol=tol,
        scale_to_liquidity=scale_to_liquidity,
        include_redundant_zero_strike_check=False,
        include_spot_negative_price_check=True,
    )

    summary_df = arbitrages_to_dataframe(arbs)
    legs_df = arbitrage_legs_to_dataframe(arbs)

    return market_df, arbs, summary_df, legs_df


# =============================================================================
# 7. Exemple d'utilisation
# =============================================================================

# =============================================================================
# 7. Exemple d'utilisation avec ton market depth
# =============================================================================

if __name__ == "__main__":

    class OrderDepth:
        """
        Classe minimale pour tester le script localement.

        Dans ton environnement de trading, cette classe existe probablement déjà.
        Si c'est le cas, supprime cette définition.
        """
        def __init__(self, buy_orders=None, sell_orders=None):
            self.buy_orders = buy_orders or {}
            self.sell_orders = sell_orders or {}

        def __repr__(self):
            return (
                f"OrderDepth("
                f"buy_orders={self.buy_orders}, "
                f"sell_orders={self.sell_orders})"
            )

    order_depths = {'VEV_6000': OrderDepth(buy_orders={0: 27}, sell_orders={1: -27}), 'VEV_5000': OrderDepth(buy_orders={244: 30}, sell_orders={250: -9, 251: -21}), 'HYDROGEL_PACK': OrderDepth(buy_orders={9983: 15, 9980: 21}, sell_orders={9999: -15, 10001: -21}), 'VEV_4000': OrderDepth(buy_orders={1230: 15, 1227: 24}, sell_orders={1251: -15, 1253: -24}), 'VEV_5100': OrderDepth(buy_orders={161: 9, 160: 21}, sell_orders={165: -30}), 'VELVETFRUIT_EXTRACT': OrderDepth(buy_orders={5238: 24, 5237: 40}, sell_orders={5243: -64}), 'VEV_5200': OrderDepth(buy_orders={93: 9, 92: 21}, sell_orders={96: -30}), 'VEV_5300': OrderDepth(buy_orders={45: 27}, sell_orders={47: -27}), 'VEV_5400': OrderDepth(buy_orders={15: 27}, sell_orders={16: -27}), 'VEV_6500': OrderDepth(buy_orders={0: 17}, sell_orders={1: -17}), 'VEV_5500': OrderDepth(buy_orders={7: 27}, sell_orders={8: -27}), 'VEV_4500': OrderDepth(buy_orders={732: 9, 730: 21}, sell_orders={748: -9, 750: -21})}

    market_df, arbs, summary_df, legs_df = find_arbitrages_from_orderbook(
        order_depths=order_depths,
        spot_symbol="VELVETFRUIT_EXTRACT",
        option_prefix="VEV_",
        tol=1e-12,
        scale_to_liquidity=True,
    )

    print("\n==============================")
    print("DATAFRAME DE MARCHÉ")
    print("==============================")
    print(market_df.to_string(index=False))

    print("\n==============================")
    print("RÉSUMÉ DES ARBITRAGES")
    print("==============================")

    if summary_df.empty:
        print("Aucun arbitrage explicite détecté.")
    else:
        print(summary_df.to_string(index=False))

    print("\n==============================")
    print("JAMBES À EXÉCUTER")
    print("==============================")

    if legs_df.empty:
        print("Aucune jambe à exécuter.")
    else:
        print(legs_df.to_string(index=False))

    if arbs:
        print("\n==============================")
        print("DÉTAIL DU PREMIER ARBITRAGE")
        print("==============================")

        first_arb = arbs[0]

        print("Type d'arbitrage:")
        print(first_arb["arbitrage"])

        print("\nCondition violée:")
        print(first_arb["condition"])

        print("\nGain initial par unité:")
        print(first_arb["violation_per_unit"])

        print("\nTaille exploitable:")
        print(first_arb["base_qty"])

        print("\nCash-flow initial total:")
        print(first_arb["initial_cashflow"])

        print("\nJambes:")
        print(first_arb["legs"].to_string(index=False))

        print("\nPayoff terminal du premier arbitrage:")
        s_values = [
            0,
            4000,
            4500,
            5000,
            5100,
            5200,
            5300,
            5400,
            5500,
            6000,
            6500,
            8000,
        ]

        payoff_df = payoff_table_for_arbitrage(first_arb, s_values)
        print(payoff_df.to_string(index=False))

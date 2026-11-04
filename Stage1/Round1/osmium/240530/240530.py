"""
Trader pour ASH_COATED_OSMIUM — v2 avec cross sur mispricing
==============================================================

Changements vs v1 :
- EDGE_TAKER constant (5) → seuil adaptatif au spread (0.20 * spread)
- Taker size croît avec l'intensité du mispricing (5-15 au lieu de 5 fixe)
- Détection "high conviction" : les 2 composantes d'edge du même signe → taille doublée

Logique économique du cross :
    Coût du cross ≈ spread / 2
    Gain attendu ≈ edge × HL ≈ edge × 2.5
    Break-even   : edge × 2.5 > spread / 2  →  edge > spread / 5 ≈ 0.20 * spread
"""

from __future__ import annotations
import json
try:
    from datamodel import Order, OrderDepth, TradingState
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState

PRODUCT = "ASH_COATED_OSMIUM"

# ───────────────────────────────────────────────────────────────────────────────
# Paramètres calibrés
# ───────────────────────────────────────────────────────────────────────────────
POS_LIMIT      = 80

SIZE_INNER     = 8
SIZE_OUTER     = 8
SIZE_TAKER_MIN = 5       # taille de taker au seuil
SIZE_TAKER_MAX = 15      # taille de taker quand edge très fort
SIZE_TAKER_STRONG = 20   # taille quand high conviction (2 signaux alignés)

# Modèle prédictif (Ridge OLS, R²=0.349)
MU             = 10_000.0
ALPHA_IMB      = 4.72
BETA_DEV       = -0.0284

# Seuils de quoting skew (inchangés)
EDGE_SKEW_LIGHT = 1.0
EDGE_SKEW_HARD  = 2.0

# ✨ NOUVEAU : seuil de taker adaptatif au spread
# edge_taker = EDGE_TAKER_K * spread
# Pour spread=16 → seuil = 3.2 (au lieu de 5 constant)
# Pour spread=10 → seuil = 2.0 (cross plus facile sur spread serré)
# Pour spread=25 → seuil = 5.0 (cross plus dur sur spread large)
EDGE_TAKER_K   = 0.3

# Seuils d'inventaire (inchangés)
INV_SOFT       = 30
INV_HARD       = 50
# ───────────────────────────────────────────────────────────────────────────────


class Trader:
    """
    Market-making dual-layer + taker adaptatif sur mispricing.
    """

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos    = state.position.get(PRODUCT, 0)
        depth  = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        if not depth or not depth.buy_orders or not depth.sell_orders:
            orders.append(Order(PRODUCT, 1,       min(SIZE_INNER, POS_LIMIT - pos)))
            orders.append(Order(PRODUCT, 10**9,  -min(SIZE_INNER, POS_LIMIT + pos)))
            return {PRODUCT: orders}, 0, state.traderData or ""

        bid_px = max(depth.buy_orders.keys())
        ask_px = min(depth.sell_orders.keys())
        bid_vol = depth.buy_orders[bid_px]
        ask_vol = -depth.sell_orders[ask_px]
        spread = ask_px - bid_px
        mid    = (ask_px + bid_px) / 2.0

        # ── Signaux ───────────────────────────────────────────────────────────
        imb = (bid_vol - ask_vol) / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0
        alpha_comp = ALPHA_IMB * imb                # composante microstructure
        dev_comp   = BETA_DEV * (mid - MU)          # composante mean-reversion
        edge       = alpha_comp + dev_comp

        # ✨ High conviction : les deux signaux convergent
        signals_aligned = (alpha_comp * dev_comp > 0) and (abs(alpha_comp) > 0.3) and (abs(dev_comp) > 0.3)

        # ── Tailles de base ───────────────────────────────────────────────────
        bid_inner = SIZE_INNER
        bid_outer = SIZE_OUTER
        ask_inner = SIZE_INNER
        ask_outer = SIZE_OUTER

        # ── SKEW PAR EDGE (inchangé) ──────────────────────────────────────────
        if edge > EDGE_SKEW_HARD:
            ask_inner = max(2, SIZE_INNER // 3)
            ask_outer = max(2, SIZE_OUTER // 3)
            bid_inner = SIZE_INNER + 4
        elif edge > EDGE_SKEW_LIGHT:
            ask_inner = max(2, SIZE_INNER // 2)
        elif edge < -EDGE_SKEW_HARD:
            bid_inner = max(2, SIZE_INNER // 3)
            bid_outer = max(2, SIZE_OUTER // 3)
            ask_inner = SIZE_INNER + 4
        elif edge < -EDGE_SKEW_LIGHT:
            bid_inner = max(2, SIZE_INNER // 2)

        # ── SKEW PAR INVENTAIRE (inchangé) ────────────────────────────────────
        if pos > INV_HARD:
            bid_inner = max(2, bid_inner // 3)
            bid_outer = max(2, bid_outer // 3)
            ask_inner = int(ask_inner * 1.5)
        elif pos > INV_SOFT:
            bid_inner = max(2, bid_inner // 2)
        elif pos < -INV_HARD:
            ask_inner = max(2, ask_inner // 3)
            ask_outer = max(2, ask_outer // 3)
            bid_inner = int(bid_inner * 1.5)
        elif pos < -INV_SOFT:
            ask_inner = max(2, ask_inner // 2)

        # ── Cap par limite de position ────────────────────────────────────────
        bid_room = POS_LIMIT - pos
        ask_room = POS_LIMIT + pos

        bid_inner = min(bid_inner, bid_room)
        bid_outer = min(bid_outer, max(0, bid_room - bid_inner))
        ask_inner = min(ask_inner, ask_room)
        ask_outer = min(ask_outer, max(0, ask_room - ask_inner))

        # ── ORDRES PASSIFS — DUAL LAYER (inchangé) ────────────────────────────
        if spread > 2:
            if bid_inner > 0:
                orders.append(Order(PRODUCT, bid_px + 1, bid_inner))
            if ask_inner > 0:
                orders.append(Order(PRODUCT, ask_px - 1, -ask_inner))

        if bid_outer > 0:
            orders.append(Order(PRODUCT, bid_px, bid_outer))
        if ask_outer > 0:
            orders.append(Order(PRODUCT, ask_px, -ask_outer))

        # ── ✨ TAKER ADAPTATIF AU SPREAD ──────────────────────────────────────
        # Seuil dynamique : plus le spread est serré, plus on cross facilement
        edge_taker_threshold = EDGE_TAKER_K * spread

        # Force du signal : 1.0 = juste au seuil, 2.0 = double, etc.
        taker_strength = abs(edge) / max(edge_taker_threshold, 1e-6)

        if taker_strength >= 1.0:
            # Taille proportionnelle à la force, bornée
            if signals_aligned and taker_strength >= 1.5:
                # ✨ High conviction : on prend gros
                taker_size = SIZE_TAKER_STRONG
            else:
                # Taille normale, croît avec la force
                taker_size = int(SIZE_TAKER_MIN + (SIZE_TAKER_MAX - SIZE_TAKER_MIN)
                                 * min(taker_strength - 1.0, 1.0))

            if edge > 0 and bid_room >= SIZE_TAKER_MIN:
                # Edge positif → ça va monter → on achète au best ask
                qty = min(taker_size, bid_room, ask_vol)
                if qty > 0:
                    orders.append(Order(PRODUCT, ask_px, qty))
            elif edge < 0 and ask_room >= SIZE_TAKER_MIN:
                # Edge négatif → ça va baisser → on vend au best bid
                qty = min(taker_size, ask_room, bid_vol)
                if qty > 0:
                    orders.append(Order(PRODUCT, bid_px, -qty))

        # ── État sérialisé ────────────────────────────────────────────────────
        st_out = json.dumps({
            "mid": mid,
            "spread": spread,
            "imb": round(imb, 4),
            "edge": round(edge, 3),
            "aligned": signals_aligned,
            "pos": pos,
        })

        return {PRODUCT: orders}, 0, st_out
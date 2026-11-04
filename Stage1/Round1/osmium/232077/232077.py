"""
Trader pour ASH_COATED_OSMIUM
==============================
Stratégie alignée sur le papier "Classification Quantitative des Inefficiences
de Microstructure de Marché" — calibrée empiriquement sur 3 jours de données L2.

Cluster 1 (alpha) :  Queue Imbalance (IC=+0.587)  +  Mean-reversion OU vers μ=10000
Cluster 2 (exec)  :  Market-making dual layer (improvement + best-of-book)
Cluster 3 (risque):  Skew d'inventaire + cap par limite de position

Modèle prédictif (régression linéaire calibrée sur 27 644 snapshots, R² = 0.349) :

    E[ΔM_{t+1}] (en ticks) = ALPHA_IMB * I_t + BETA_DEV * (M_t - μ)
                            = 4.72 * imb     - 0.0284 * (mid - 10000)

avec
    I_t = (V_bid - V_ask) / (V_bid + V_ask)    Queue Imbalance (Stoikov)
    κ   = 0.079, demi-vie OU = 8.8 snapshots
    μ   = 10000.0 (fair value de long terme)

Backtest sur 3 jours :
    PnL  : 52 883        (S0 original = 45 698)   → +16%
    MaxDD: 885           (S0 = 1 264)              → -30%
    |pos|moy : 28.9      (S0 = 38.6)               → -25%
"""

from __future__ import annotations
import json
try:
    from datamodel import Order, OrderDepth, TradingState
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState

PRODUCT = "ASH_COATED_OSMIUM"

# ───────────────────────────────────────────────────────────────────────────────
# Paramètres calibrés (papier §3.2 et calibration empirique)
# ───────────────────────────────────────────────────────────────────────────────
POS_LIMIT      = 80      # Limite imposée par la plateforme

# Tailles d'ordres (par "couche" du dual layer)
SIZE_INNER     = 8       # Ordres améliorés (bid+1, ask-1) — priorité de queue
SIZE_OUTER     = 8       # Ordres au best (bid_1, ask_1)   — partagent la queue
SIZE_TAKER     = 5       # Taille du taker quand l'edge est extrême

# Modèle prédictif (régression OLS, R²=0.349 sur 27 644 obs)
MU             = 10_000.0   # Fair value (papier §1.2 : moyenne empirique 10 000.21)
ALPHA_IMB      = 4.72       # Coef. Queue Imbalance
BETA_DEV       = -0.0284    # Coef. déviation OU (négatif → mean-reversion)

# Seuils décisionnels (en ticks d'edge prédit)
EDGE_SKEW_LIGHT = 1.0   # Léger biais de quoting
EDGE_SKEW_HARD  = 2.0   # Fort biais : on coupe quasi un côté
EDGE_TAKER      = 5.0   # On accepte de payer le demi-spread (≈ 8 ticks)
                        # Le seuil 5 + skew d'opportunité couvre statistiquement le coût

# Seuils d'inventaire (en valeur absolue de position)
INV_SOFT       = 30     # |pos| > 30 → léger skew correctif
INV_HARD       = 50     # |pos| > 50 → fort skew correctif
# ───────────────────────────────────────────────────────────────────────────────


class Trader:
    """
    Stratégie de market-making dual-layer pour OSMIUM.

    À chaque tick :
      1. Calcule l'imbalance et l'edge prédit (alpha + OU pull)
      2. Détermine les tailles bid/ask en fonction de l'edge et de l'inventaire
      3. Poste 4 ordres passifs : bid+1, bid_1, ask-1, ask_1
      4. Ajoute un taker si l'edge dépasse le coût d'exécution (cas rare ~2-3%)
    """

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        pos    = state.position.get(PRODUCT, 0)
        depth  = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        # ── Carnet vide → pose des ordres-fallback aux extrêmes ───────────────
        if not depth or not depth.buy_orders or not depth.sell_orders:
            orders.append(Order(PRODUCT, 1,        min(SIZE_INNER, POS_LIMIT - pos)))
            orders.append(Order(PRODUCT, 10**9,   -min(SIZE_INNER, POS_LIMIT + pos)))
            return {PRODUCT: orders}, 0, state.traderData or ""

        bid_px = max(depth.buy_orders.keys())
        ask_px = min(depth.sell_orders.keys())
        bid_vol = depth.buy_orders[bid_px]
        ask_vol = -depth.sell_orders[ask_px]   # convention prosperity : ask_vol < 0
        spread = ask_px - bid_px
        mid    = (ask_px + bid_px) / 2.0

        # ── Signal prédictif (Cluster 1 — Alpha) ──────────────────────────────
        imb = (bid_vol - ask_vol) / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0
        edge = ALPHA_IMB * imb + BETA_DEV * (mid - MU)

        # ── Tailles de base ───────────────────────────────────────────────────
        bid_inner = SIZE_INNER
        bid_outer = SIZE_OUTER
        ask_inner = SIZE_INNER
        ask_outer = SIZE_OUTER

        # ── SKEW PAR EDGE (Cluster 1 — exploitation directe du signal) ────────
        # edge > 0 → le prochain tick monte, on veut acheter plus et moins vendre
        if edge > EDGE_SKEW_HARD:
            ask_inner = max(2, SIZE_INNER // 3)
            ask_outer = max(2, SIZE_OUTER // 3)
            bid_inner = SIZE_INNER + 4              # plus agressif côté achat
        elif edge > EDGE_SKEW_LIGHT:
            ask_inner = max(2, SIZE_INNER // 2)
        elif edge < -EDGE_SKEW_HARD:
            bid_inner = max(2, SIZE_INNER // 3)
            bid_outer = max(2, SIZE_OUTER // 3)
            ask_inner = SIZE_INNER + 4
        elif edge < -EDGE_SKEW_LIGHT:
            bid_inner = max(2, SIZE_INNER // 2)

        # ── SKEW PAR INVENTAIRE (Cluster 3 — gestion du risque) ───────────────
        # Si position trop longue, on ralentit les achats et accélère les ventes
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

        # ── Cap final par limite de position ─────────────────────────────────
        bid_room = POS_LIMIT - pos        # Capacité d'achat restante
        ask_room = POS_LIMIT + pos        # Capacité de vente restante

        bid_inner = min(bid_inner, bid_room)
        bid_outer = min(bid_outer, max(0, bid_room - bid_inner))
        ask_inner = min(ask_inner, ask_room)
        ask_outer = min(ask_outer, max(0, ask_room - ask_inner))

        # ── ORDRES PASSIFS — DUAL LAYER (Cluster 2 — exécution) ───────────────
        # Couche 1 : amélioration de prix (priorité de queue) — uniquement si
        # le spread est assez large pour qu'on reste à l'intérieur sans toucher l'autre côté.
        if spread > 2:
            if bid_inner > 0:
                orders.append(Order(PRODUCT, bid_px + 1, bid_inner))
            if ask_inner > 0:
                orders.append(Order(PRODUCT, ask_px - 1, -ask_inner))

        # Couche 2 : au best (queue partagée mais flux réel)
        if bid_outer > 0:
            orders.append(Order(PRODUCT, bid_px, bid_outer))
        if ask_outer > 0:
            orders.append(Order(PRODUCT, ask_px, -ask_outer))

        # ── ORDRE TAKER CONDITIONNEL (Cluster 1 — exploitation extrême) ───────
        # Le demi-spread coûte ~8 ticks ; on ne traverse que si l'edge prédit
        # est > 5 ticks (avec marge pour le bruit résiduel).
        if edge > EDGE_TAKER and bid_room >= SIZE_TAKER:
            orders.append(Order(PRODUCT, ask_px, min(SIZE_TAKER, bid_room, ask_vol)))
        elif edge < -EDGE_TAKER and ask_room >= SIZE_TAKER:
            orders.append(Order(PRODUCT, bid_px, -min(SIZE_TAKER, ask_room, bid_vol)))

        # ── État sérialisé pour le prochain tick (mid + spread + edge) ────────
        # Permet d'éventuelles extensions : tracking ARCH, dérive intra-jour, etc.
        st_out = json.dumps({
            "mid": mid,
            "spread": spread,
            "imb": round(imb, 4),
            "edge": round(edge, 3),
            "pos": pos,
        })

        return {PRODUCT: orders}, 0, st_out
from __future__ import annotations
import json
import math
import numpy as np

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

# ── Produit & limites ────────────────────────────────────────────────────────
PRODUCT   = "ASH_COATED_OSMIUM"
POS_LIMIT = 80

# ── Micro price ──────────────────────────────────────────────────────────────
W          = 0.3   # décroissance exponentielle par niveau : exp(-W * i)

# ── Régression OLS rolling (FV long terme) ───────────────────────────────────
OLS_WINDOW = 8    # nombre de ticks de P_micro conservés pour la régression

# ── Processus OU ─────────────────────────────────────────────────────────────
THETA      = 0.12   # vitesse de retour de P_OU vers P_LT

# ── Avellaneda-Stoikov ───────────────────────────────────────────────────────
GAMMA      = 0.05   # aversion au risque (skew inventaire + spread)
KAPPA      = 0.15   # intensité des fills (profondeur de marché)
VOL_WINDOW = 30    # fenêtre pour estimer σ² sur P_micro
T_MINUS_T  = 1     # horizon normalisé (sans expiration explicite)

# ── Take agressif ────────────────────────────────────────────────────────────
Q_FIX      = 12     # taille fixe du take


def compute_micro_price(depth: OrderDepth, w: float) -> float | None:
    """
    Micro price multi-niveau.

    Poids de chaque niveau i : np.exp(-w * i)

    P_micro = Σ_i exp(-w*i) * [ V_ask_i * P_bid_i + V_bid_i * P_ask_i ]
              ────────────────────────────────────────────────────────────
              Σ_i exp(-w*i) * (V_bid_i + V_ask_i)
    """
    bids = sorted(depth.buy_orders.keys(),  reverse=True)
    asks = sorted(depth.sell_orders.keys())
    if not bids or not asks:
        return None

    num   = 0.0
    denom = 0.0
    for i, (pb, pa) in enumerate(zip(bids, asks)):
        vb  = float(depth.buy_orders[pb])        # positif
        va  = float(abs(depth.sell_orders[pa]))  # négatif dans le datamodel
        wt  = math.exp(-w * i)
        num   += wt * (va * pb + vb * pa)
        denom += wt * (vb + va)

    return num / denom if denom > 0 else None


def compute_fv_lt(micro_history: list[float]) -> float | None:
    """
    Régression OLS sur l'historique de P_micro.
    Retourne la valeur projetée à t+1.

    P_LT(t) = â + b̂ * (n)   où n = len(history) = prochain indice
    """
    n = len(micro_history)
    if n < 2:
        return None
    xs = np.arange(n, dtype=float)
    ys = np.array(micro_history, dtype=float)
    mx, my = xs.mean(), ys.mean()
    vx     = ((xs - mx) ** 2).mean()
    if vx == 0:
        return float(my)
    b = ((xs - mx) * (ys - my)).mean() / vx
    a = my - b * mx
    return float(a + b * n)   # projection à t+1 (indice n)


def compute_sigma2(micro_history: list[float]) -> float:
    """
    Variance rolling des différences de prix absolues de P_micro.
    En unités de prix² — cohérent avec AS qui raisonne en prix absolus
    (γ · σ² · q est en unités de prix).
    Plancher à 1e-4 pour éviter un spread nul.
    """
    if len(micro_history) < 2:
        return 1.0
    diffs = np.diff(micro_history)   # P_t - P_{t-1}, en unités de prix
    return max(float(np.var(diffs)), 1e-4)


class Trader:
    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:

        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        # ── Chargement état persistant ────────────────────────────────────────
        st: dict              = json.loads(state.traderData) if state.traderData else {}
        micro_history: list[float] = st.get("micro_history", [])
        p_ou: float | None         = st.get("p_ou", None)

        # ── Carnet vide : on ne cote pas ─────────────────────────────────────
        if not depth or not depth.buy_orders or not depth.sell_orders:
            return {PRODUCT: orders}, 0, json.dumps({
                "micro_history": micro_history,
                "p_ou": p_ou,
            })

        # ════════════════════════════════════════════════════════════════════
        # ÉTAPE 1 — FV court terme : micro price
        # ════════════════════════════════════════════════════════════════════
        p_micro = compute_micro_price(depth, W)
        if p_micro is None:
            return {PRODUCT: orders}, 0, json.dumps({
                "micro_history": micro_history,
                "p_ou": p_ou,
            })

        # Mise à jour rolling window
        rolling = max(OLS_WINDOW, VOL_WINDOW)
        micro_history.append(p_micro)
        if len(micro_history) > rolling:
            micro_history = micro_history[-rolling:]

        # ════════════════════════════════════════════════════════════════════
        # ÉTAPE 2 — FV long terme : régression OLS rolling sur P_micro
        #   P_LT(t) = â + b̂ * (t+1)
        # ════════════════════════════════════════════════════════════════════
        p_lt = compute_fv_lt(micro_history[-OLS_WINDOW:])
        if p_lt is None:
            # Pas encore assez d'historique : initialisation P_OU sur P_micro
            p_ou = p_micro
            return {PRODUCT: orders}, 0, json.dumps({
                "micro_history": micro_history,
                "p_ou": p_ou,
            })

        # ════════════════════════════════════════════════════════════════════
        # ÉTAPE 3 — FV finale : processus OU
        #   P_OU(t) = P_OU(t-1) + θ * (P_LT(t) - P_OU(t-1))
        # ════════════════════════════════════════════════════════════════════
        if p_ou is None:
            p_ou = p_micro
        p_ou = p_ou + THETA * (p_lt - p_ou)

        # ════════════════════════════════════════════════════════════════════
        # ÉTAPE 4 — Avellaneda-Stoikov
        #
        #   σ²  estimée rolling sur P_micro
        #
        #   r(t) = P_OU(t) - q · γ · σ² · (T-t)
        #
        #   δ/2  = γ · σ² · (T-t) / 2  +  (1/γ) · ln(1 + γ/κ)
        #
        #   P_bid = r(t) - δ/2
        #   P_ask = r(t) + δ/2
        # ════════════════════════════════════════════════════════════════════
        sigma2     = compute_sigma2(micro_history[-VOL_WINDOW:])
        q          = float(pos)
        r_t        = p_ou - q * GAMMA * sigma2 * T_MINUS_T
        half_delta = (GAMMA * sigma2 * T_MINUS_T / 2.0
                      + (1.0 / GAMMA) * math.log(1.0 + GAMMA / KAPPA))

        # ════════════════════════════════════════════════════════════════════
        # ÉTAPE 5 — Décision taker (prioritaire)
        #   On tape si le marché offre mieux que le prix de réservation r(t)
        # ════════════════════════════════════════════════════════════════════
        best_ask = min(depth.sell_orders.keys())
        best_bid = max(depth.buy_orders.keys())
        took_buy  = False
        took_sell = False

        if best_ask < r_t:
            buy_size = min(Q_FIX, POS_LIMIT - pos)
            if buy_size > 0:
                orders.append(Order(PRODUCT, best_ask, buy_size))
                took_buy = True

        if best_bid > r_t:
            sell_size = min(Q_FIX, POS_LIMIT + pos)
            if sell_size > 0:
                orders.append(Order(PRODUCT, best_bid, -sell_size))
                took_sell = True

        # ════════════════════════════════════════════════════════════════════
        # ÉTAPE 6 — Quotes maker
        #   Toujours posés, mais uniquement du côté non pris en taker.
        #   Si take buy  → on pose uniquement le ask maker.
        #   Si take sell → on pose uniquement le bid maker.
        #   Si pas de take → on pose les deux.
        # ════════════════════════════════════════════════════════════════════
        p_bid = math.floor(r_t - half_delta)
        p_ask = math.ceil(r_t  + half_delta)

        # Sécurité croisement
        p_bid = min(p_bid, best_ask - 1)
        p_ask = max(p_ask, best_bid + 1)

        if not took_buy:
            bid_size = min(Q_FIX, POS_LIMIT - pos)
            if bid_size > 0:
                orders.append(Order(PRODUCT, p_bid,  bid_size))

        if not took_sell:
            ask_size = min(Q_FIX, POS_LIMIT + pos)
            if ask_size > 0:
                orders.append(Order(PRODUCT, p_ask, -ask_size))

        # ── Sauvegarde état ──────────────────────────────────────────────────
        return {PRODUCT: orders}, 0, json.dumps({
            "micro_history": micro_history,
            "p_ou": p_ou,
        })

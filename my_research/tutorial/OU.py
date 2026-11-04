"""
TOMATOES Market Making Strategy — avec processus Ornstein-Uhlenbeck
====================================================================

Fair value model:
  EMA of weighted mid-price (all book levels) + L2 imbalance adjustment
  + correction OU (mean-reversion vers theta).

  Weighted mid = VWAP-bid * ask_vol + VWAP-ask * bid_vol, using ALL levels.
  L2 imbalance = (bid_L2_vol - ask_L2_vol) / (bid_L2_vol + ask_L2_vol)

  Processus OU  (Ornstein-Uhlenbeck discret) :
    theta    = moyenne long-terme estimée par EMA lente (ALPHA_OU_THETA)
    kappa    = vitesse de retour estimée sur la déviation observée (ALPHA_OU_KAPPA)
    ou_pull  = kappa * (theta - wmid)    [force de rappel courante]
    FV = EMA(wmid) + L2_WEIGHT * l2_imb * spread + OU_WEIGHT * ou_pull

  L'ajout OU permet de :
    1. Anticiper le mean-reversion sur un produit commodité comme TOMATOES.
    2. Amplifier gamma quand le prix dévie fortement de theta (position plus risquée).
    3. Resserrer le spread quand la force de retour est forte (plus de chance de fill
       et de PnL sur la convergence).

Reservation price (Avellaneda-Stoikov, gamma dynamique) :
  dist_norm = |wmid - theta| / (sigma + 1e-9)   # nb de sigmas hors équilibre
  gamma_eff = GAMMA * (1 + OU_GAMMA_SCALE * dist_norm)
  r = FV - gamma_eff * sigma * q

Spread OU-ajusté :
  reversion_strength = kappa * |theta - wmid| / (sigma + 1e-9)   ∈ [0, 1] (clampé)
  half_spread = (BASE_HALF_SPREAD + VOL_SPREAD_FACTOR * sigma)
                * (1 - OU_SPREAD_SHRINK * reversion_strength)

Aggressive taking:
  Cross the market when ask < FV - TAKE_EDGE or bid > FV + TAKE_EDGE.

Position management:
  - soft_limit  (50%) -> taper bid/ask size on the risky side
  - reduce_limit (70%) -> reduce-only mode
"""

from __future__ import annotations

import json
import math

try:
    from datamodel import Order, OrderDepth, TradingState  # type: ignore[import]
except ImportError:
    from prosperity4bt.domain.datamodel import Order, OrderDepth, TradingState  # type: ignore[import]

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
PRODUCT = "TOMATOES"
POS_LIMIT = 80

# Fair value
ALPHA_WMID  = 0.4       # EMA decay for weighted mid-price
L2_WEIGHT   = 0.10      # L2 imbalance adjustment weight
ALPHA_VAR   = 0.15      # EMA decay for spread-variance estimate

# OU parameters
ALPHA_OU_THETA = 0.005  # EMA très lente pour la moyenne long-terme θ
                        # (~200 ticks de mémoire — capture le niveau d'équilibre stable)
ALPHA_OU_KAPPA = 0.05   # EMA pour estimer κ (vitesse de retour observée)
                        # (~20 ticks — s'adapte aux régimes de volatilité)
OU_WEIGHT      = 0.50   # Poids de la correction OU dans le fair value
                        # 0.30 = contribution modérée, évite de sur-réagir au signal
OU_GAMMA_SCALE = 5.5   # Amplification de gamma quand loin de theta
                        # gamma_eff = GAMMA * (1 + 0.5 * dist_norm)
OU_SPREAD_SHRINK = 0.3 # Réduction max du spread quand la force de retour est forte
                        # 0.20 = spread réduit de 20% au maximum (évite de se retrouver
                        # à l'intérieur du bid-ask du marché)

# Spread
BASE_HALF_SPREAD  = 2   # ticks on each side (inside the market's ~7-tick half-spread)
VOL_SPREAD_FACTOR = 0.2 # additional half-spread per tick of realised volatility
LEVELS    = 2           # stacked quote levels per side
LEVEL_GAP = 1           # tick gap between levels

# Inventory skew (base — amplifié dynamiquement par gamma_eff si OU activé)
GAMMA = 0.003

# Order sizing
MAX_SIZE = 10           # max qty per quote level

# Aggressive taking
TAKE_EDGE = 2           # take when market price beats FV by this many ticks

# Position thresholds
SOFT_RATIO   = 0.50     # start tapering risky-side quotes at this fraction of limit
REDUCE_RATIO = 0.70     # reduce-only mode above this fraction of limit


# ─────────────────────────────────────────────────────────────────────────────
# Persistent state
# ─────────────────────────────────────────────────────────────────────────────
class State:
    def __init__(
        self,
        ema_wmid:  float = 5000.0,
        ema_var:   float = 49.0,
        ou_theta:  float = 5000.0,  # moyenne long-terme OU
        ou_kappa:  float = 0.0,     # vitesse de retour estimée OU
    ) -> None:
        self.ema_wmid = ema_wmid
        self.ema_var  = ema_var
        self.ou_theta = ou_theta
        self.ou_kappa = ou_kappa

    def to_json(self) -> str:
        return json.dumps({
            "ema_wmid":  self.ema_wmid,
            "ema_var":   self.ema_var,
            "ou_theta":  self.ou_theta,
            "ou_kappa":  self.ou_kappa,
        })

    @classmethod
    def from_json(cls, text: str) -> "State":
        try:
            d = json.loads(text)
            return cls(
                ema_wmid = float(d.get("ema_wmid",  5000.0)),
                ema_var  = float(d.get("ema_var",   49.0)),
                ou_theta = float(d.get("ou_theta",  5000.0)),
                ou_kappa = float(d.get("ou_kappa",  0.0)),
            )
        except Exception:
            return cls()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def compute_weighted_mid(depth: OrderDepth) -> float | None:
    """Weighted mid-price using ALL book levels (VWAP-based)."""
    if not depth.buy_orders or not depth.sell_orders:
        return None
    total_bval = sum(p * abs(depth.buy_orders[p]) for p in depth.buy_orders)
    total_aval = sum(p * abs(depth.sell_orders[p]) for p in depth.sell_orders)
    total_bvol = sum(abs(depth.buy_orders[p]) for p in depth.buy_orders)
    total_avol = sum(abs(depth.sell_orders[p]) for p in depth.sell_orders)
    if total_bvol == 0 or total_avol == 0:
        return (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
    vwap_bid = total_bval / total_bvol
    vwap_ask = total_aval / total_avol
    return (vwap_bid * total_avol + vwap_ask * total_bvol) / (total_avol + total_bvol)


def compute_l2_imbalance(depth: OrderDepth) -> float:
    """Imbalance at the second level of the order book."""
    sorted_bids = sorted(depth.buy_orders.keys(), reverse=True)
    sorted_asks = sorted(depth.sell_orders.keys())
    bv2 = abs(depth.buy_orders[sorted_bids[1]]) if len(sorted_bids) > 1 else 0
    av2 = abs(depth.sell_orders[sorted_asks[1]]) if len(sorted_asks) > 1 else 0
    if bv2 + av2 == 0:
        return 0.0
    return (bv2 - av2) / (bv2 + av2)


def to_tick(price: float) -> int:
    return int(round(price))


# ─────────────────────────────────────────────────────────────────────────────
# Trader
# ─────────────────────────────────────────────────────────────────────────────
class Trader:
    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:

        # ── Restore persistent state ──────────────────────────────────────────
        st    = State.from_json(state.traderData) if state.traderData else State()
        pos   = state.position.get(PRODUCT, 0)
        depth = state.order_depths.get(PRODUCT)
        orders: list[Order] = []

        if depth is None or (not depth.buy_orders and not depth.sell_orders):
            return {PRODUCT: orders}, 0, st.to_json()

        # ── Weighted mid ──────────────────────────────────────────────────────
        wmid = compute_weighted_mid(depth)
        if wmid is None:
            return {PRODUCT: orders}, 0, st.to_json()

        # ── Mettre à jour l'EMA du mid-price ─────────────────────────────────
        st.ema_wmid = ALPHA_WMID * wmid + (1.0 - ALPHA_WMID) * st.ema_wmid

        # ── Processus Ornstein-Uhlenbeck ──────────────────────────────────────
        # 1. Mettre à jour theta (moyenne long-terme) avec une EMA très lente.
        #    theta représente le niveau d'équilibre "naturel" du marché.
        prev_theta = st.ou_theta
        st.ou_theta = ALPHA_OU_THETA * wmid + (1.0 - ALPHA_OU_THETA) * st.ou_theta

        # 2. Estimer kappa (vitesse de retour) à partir de la déviation observée.
        #    Dans un processus OU discret : dx = -kappa*(x - theta)*dt + dW
        #    On approche kappa par : |Δwmid| / (|wmid_prev - theta_prev| + eps)
        #    puis on lisse par EMA pour éviter le bruit tick-à-tick.
        deviation_prev = abs(wmid - prev_theta)
        delta_wmid     = abs(wmid - (st.ema_wmid / ALPHA_WMID *
                            (1.0 - (1.0 - ALPHA_WMID))))  # ≈ variation récente du mid
        # Version robuste : kappa_obs proportionnel au rappel relatif
        if deviation_prev > 1e-6:
            kappa_obs = min(1.0, abs(wmid - prev_theta) /
                           (deviation_prev + 1e-9) * ALPHA_WMID)
        else:
            kappa_obs = 0.0
        st.ou_kappa = ALPHA_OU_KAPPA * kappa_obs + (1.0 - ALPHA_OU_KAPPA) * st.ou_kappa

        # 3. Force de rappel OU courante (en ticks).
        #    Si wmid > theta → ou_pull négatif (signal de vente / baisse FV)
        #    Si wmid < theta → ou_pull positif (signal d'achat / hausse FV)
        ou_pull = st.ou_kappa * (st.ou_theta - wmid)

        # ── Mise à jour du fair value ─────────────────────────────────────────
        spread = float(
            min(depth.sell_orders) - max(depth.buy_orders)
        ) if depth.buy_orders and depth.sell_orders else 0.0

        l2_imb = compute_l2_imbalance(depth)

        # FV combiné : EMA wmid + ajustement L2 + correction OU
        fv = st.ema_wmid \
           + L2_WEIGHT * l2_imb * spread \
           + OU_WEIGHT * ou_pull

        # ── Mise à jour variance (sigma) ──────────────────────────────────────
        if depth.buy_orders and depth.sell_orders:
            raw_spread = float(min(depth.sell_orders) - max(depth.buy_orders))
            deviation  = raw_spread - math.sqrt(st.ema_var)
            st.ema_var = max(1.0, ALPHA_VAR * deviation ** 2 + (1.0 - ALPHA_VAR) * st.ema_var)

        sigma = math.sqrt(st.ema_var)

        # ── Gamma dynamique OU ────────────────────────────────────────────────
        # Quand le prix s'éloigne de theta, la position inventaire est plus risquée
        # (le marché peut continuer à dériver avant de mean-revenir). On amplifie
        # gamma proportionnellement à la déviation normalisée.
        dist_norm = abs(wmid - st.ou_theta) / (sigma + 1e-9)   # en nb de sigmas
        gamma_eff = GAMMA * (1.0 + OU_GAMMA_SCALE * dist_norm)

        # ── Reservation price : skew vers réduction d'inventaire ─────────────
        r = fv - gamma_eff * sigma * pos

        # ── Spread OU-ajusté ──────────────────────────────────────────────────
        # Quand la force de retour OU est forte, le prix va probablement revenir
        # rapidement → on peut se permettre un spread plus serré pour capter plus
        # de fills sur la convergence.
        reversion_strength = min(1.0, st.ou_kappa * abs(st.ou_theta - wmid) / (sigma + 1e-9))
        half = (BASE_HALF_SPREAD + VOL_SPREAD_FACTOR * sigma) \
               * (1.0 - OU_SPREAD_SHRINK * reversion_strength)
        # Garantir un minimum absolu pour ne pas croiser le marché involontairement
        half = max(1.0, half)

        # ── Régimes de position ───────────────────────────────────────────────
        soft_limit   = int(POS_LIMIT * SOFT_RATIO)
        reduce_limit = int(POS_LIMIT * REDUCE_RATIO)

        wl = pos
        ws = pos

        # ── Prise agressive : croiser le marché si prix mispriced ────────────
        if depth.sell_orders:
            for ask_px in sorted(depth.sell_orders):
                if ask_px >= fv - TAKE_EDGE:
                    break
                vol = abs(depth.sell_orders[ask_px])
                qty = min(vol, MAX_SIZE * 2, POS_LIMIT - wl)
                if qty > 0:
                    orders.append(Order(PRODUCT, ask_px, qty))
                    wl += qty

        if depth.buy_orders:
            for bid_px in sorted(depth.buy_orders, reverse=True):
                if bid_px <= fv + TAKE_EDGE:
                    break
                vol = abs(depth.buy_orders[bid_px])
                qty = min(vol, MAX_SIZE * 2, ws + POS_LIMIT)
                if qty > 0:
                    orders.append(Order(PRODUCT, bid_px, -qty))
                    ws -= qty

        # ── Quotes passifs (market-making) ────────────────────────────────────
        for lvl in range(LEVELS):
            bid_px = to_tick(r - half - lvl * LEVEL_GAP)
            ask_px = to_tick(r + half + lvl * LEVEL_GAP)

            if abs(pos) >= reduce_limit:
                if pos > 0:
                    qty = min(MAX_SIZE, ws + POS_LIMIT)
                    if qty > 0:
                        orders.append(Order(PRODUCT, ask_px, -qty))
                        ws -= qty
                else:
                    qty = min(MAX_SIZE, POS_LIMIT - wl)
                    if qty > 0:
                        orders.append(Order(PRODUCT, bid_px, qty))
                        wl += qty
            else:
                bid_size = MAX_SIZE
                if pos >= soft_limit:
                    bid_size = max(1, bid_size // 3)
                qty_b = min(bid_size, POS_LIMIT - wl)
                if qty_b > 0:
                    orders.append(Order(PRODUCT, bid_px, qty_b))
                    wl += qty_b

                ask_size = MAX_SIZE
                if pos <= -soft_limit:
                    ask_size = max(1, ask_size // 3)
                qty_a = min(ask_size, ws + POS_LIMIT)
                if qty_a > 0:
                    orders.append(Order(PRODUCT, ask_px, -qty_a))
                    ws -= qty_a

        return {PRODUCT: orders}, 0, st.to_json()

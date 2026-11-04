import numpy as np
import plotly.graph_objects as go

# -----------------------------
# Paramètres du jeu
# -----------------------------

FAIR_PRICE = 920

# Prix de réserve possibles : 670, 675, ..., 920
reserves = np.arange(670, 921, 5)

# Bids testés : 671, 676, ..., 916
# Comme la condition est stricte bid > reserve,
# 671 permet d'acheter les réserves à 670,
# 676 permet d'acheter les réserves à 670 et 675, etc.
bid_grid = np.arange(671, 917, 5)

b2_grid = bid_grid.copy()
avg_b2_grid = bid_grid.copy()

# -----------------------------
# Fonction de PNL du second bid
# -----------------------------

def second_bid_value_per_trade(b2, avg_b2):
    """
    PNL par trade obtenu au second bid.

    Si b2 > avg_b2 :
        pas de pénalité, PNL = 920 - b2

    Si b2 <= avg_b2 :
        pénalité appliquée :
        PNL = (920 - b2) * ((920 - avg_b2) / (920 - b2))^3
    """
    raw_pnl = FAIR_PRICE - b2

    if b2 > avg_b2:
        return raw_pnl
    else:
        penalty = ((FAIR_PRICE - avg_b2) / (FAIR_PRICE - b2)) ** 3
        return raw_pnl * penalty


def expected_pnl_b2_only(b2, avg_b2):
    """
    PNL espéré par contrepartie si on ne considère que le second bid.

    Une contrepartie trade au second bid si :
        reserve < b2
    """
    n_traded = np.sum(reserves < b2)
    value_per_trade = second_bid_value_per_trade(b2, avg_b2)

    return (n_traded * value_per_trade) / len(reserves)


# -----------------------------
# PNL avec b1 optimisé après choix de b2
# -----------------------------

def expected_total_pnl_for_b1_b2(b1, b2, avg_b2):
    """
    PNL espéré par contrepartie avec deux bids.

    Règle :
    - Si reserve < b1 : trade à b1
    - Sinon, si reserve < b2 : trade à b2
    - Sinon : pas de trade

    On suppose ici b1 < b2 pour que le second bid ait un rôle réel.
    """
    pnl_second_trade = second_bid_value_per_trade(b2, avg_b2)

    total_pnl = 0.0

    for r in reserves:
        if b1 > r:
            total_pnl += FAIR_PRICE - b1
        elif b2 > r:
            total_pnl += pnl_second_trade
        else:
            total_pnl += 0.0

    return total_pnl / len(reserves)


def optimal_b1_given_b2(b2, avg_b2):
    """
    Trouve le meilleur b1 pour un b2 donné.

    On impose b1 < b2.
    """
    possible_b1s = bid_grid[bid_grid < b2]

    best_b1 = None
    best_pnl = -np.inf

    for b1 in possible_b1s:
        pnl = expected_total_pnl_for_b1_b2(b1, b2, avg_b2)

        if pnl > best_pnl:
            best_pnl = pnl
            best_b1 = b1

    return best_b1, best_pnl


# -----------------------------
# Construction des matrices 3D
# -----------------------------

Z_b2_only = np.zeros((len(avg_b2_grid), len(b2_grid)))
Z_total_optimized = np.zeros((len(avg_b2_grid), len(b2_grid)))
Z_best_b1 = np.zeros((len(avg_b2_grid), len(b2_grid)))

for i, avg_b2 in enumerate(avg_b2_grid):
    for j, b2 in enumerate(b2_grid):
        Z_b2_only[i, j] = expected_pnl_b2_only(b2, avg_b2)

        best_b1, best_pnl = optimal_b1_given_b2(b2, avg_b2)
        Z_total_optimized[i, j] = best_pnl
        Z_best_b1[i, j] = best_b1 if best_b1 is not None else np.nan


# -----------------------------
# Graphique 1 : PNL du second bid seul
# -----------------------------

fig_b2_only = go.Figure(
    data=[
        go.Surface(
            x=b2_grid,
            y=avg_b2_grid,
            z=Z_b2_only,
            colorscale="Viridis",
            colorbar=dict(title="PNL attendu"),
            hovertemplate=(
                "b2 = %{x}<br>"
                "avg_b2 = %{y}<br>"
                "PNL attendu b2 seul = %{z:.4f}<extra></extra>"
            ),
        )
    ]
)

fig_b2_only.update_layout(
    title="PNL attendu du second bid seul",
    scene=dict(
        xaxis_title="b2",
        yaxis_title="Moyenne des b2 des autres joueurs",
        zaxis_title="PNL attendu par contrepartie",
    ),
    width=1000,
    height=750,
)

fig_b2_only.show()


# -----------------------------
# Graphique 2 : PNL total avec b1 optimisé
# -----------------------------

fig_total = go.Figure(
    data=[
        go.Surface(
            x=b2_grid,
            y=avg_b2_grid,
            z=Z_total_optimized,
            surfacecolor=Z_best_b1,
            colorscale="Viridis",
            colorbar=dict(title="b1 optimal"),
            customdata=Z_best_b1,
            hovertemplate=(
                "b2 = %{x}<br>"
                "avg_b2 = %{y}<br>"
                "b1 optimal = %{customdata:.0f}<br>"
                "PNL total attendu = %{z:.4f}<extra></extra>"
            ),
        )
    ]
)

fig_total.update_layout(
    title="PNL total attendu avec b1 optimisé pour chaque b2",
    scene=dict(
        xaxis_title="b2",
        yaxis_title="Moyenne des b2 des autres joueurs",
        zaxis_title="PNL total attendu par contrepartie",
    ),
    width=1000,
    height=750,
)

fig_total.show()


# -----------------------------
# Meilleur couple global dans cette grille
# -----------------------------

max_index = np.unravel_index(np.nanargmax(Z_total_optimized), Z_total_optimized.shape)

best_avg_b2 = avg_b2_grid[max_index[0]]
best_b2 = b2_grid[max_index[1]]
best_b1 = Z_best_b1[max_index]
best_pnl = Z_total_optimized[max_index]

print("Meilleur point dans la grille :")
print(f"b1 optimal  = {best_b1:.0f}")
print(f"b2 optimal  = {best_b2:.0f}")
print(f"avg_b2      = {best_avg_b2:.0f}")
print(f"PNL attendu = {best_pnl:.6f}")

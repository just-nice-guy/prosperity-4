import numpy as np
from scipy.optimize import minimize_scalar
import plotly.graph_objects as go

BUDGET = 50_000

# =========================
# Fonctions du modèle
# =========================

def research(x):
    return 200_000 * np.log(1 + x) / np.log(101)

def scale(y):
    return 7 * y / 100

def speed_multiplier(rank):
    return 0.1 + 0.8 * rank

def pnl(x, y, speed):
    return research(x) * scale(y) * speed - BUDGET

# =========================
# Optimisation
# =========================

def optimal_pnl_given_z_rank(z, rank):
    v = speed_multiplier(rank)

    def objective(x):
        y = 100 - z - x
        if y < 0:
            return 1e18
        return -pnl(x, y, v)

    res = minimize_scalar(
        objective,
        bounds=(0, 100 - z),
        method="bounded"
    )

    x_opt = res.x
    y_opt = 100 - z - x_opt
    print(x_opt,y_opt,z,rank)
    pnl_opt = pnl(x_opt, y_opt, v)

    return pnl_opt


print('-'*10)
print(optimal_pnl_given_z_rank(41,0.1))
print(optimal_pnl_given_z_rank(41,0.15))
print(optimal_pnl_given_z_rank(41,0.2))
print(optimal_pnl_given_z_rank(41,0.3))
print(optimal_pnl_given_z_rank(41,0.4))
print(optimal_pnl_given_z_rank(41,0.5))
print(optimal_pnl_given_z_rank(41,0.6))
print(optimal_pnl_given_z_rank(41,0.7))
print(optimal_pnl_given_z_rank(41,0.8))

exit()

# =========================
# Grille
# =========================

z_vals = np.linspace(0, 100, 60)
rank_vals = np.linspace(0, 1, 60)

Z, R = np.meshgrid(z_vals, rank_vals)
PnL = np.zeros_like(Z)

for i in range(Z.shape[0]):
    for j in range(Z.shape[1]):
        PnL[i, j] = optimal_pnl_given_z_rank(Z[i, j], R[i, j])

# =========================
# Plot interactif
# =========================

fig = go.Figure(data=[go.Surface(
    x=Z,
    y=R,
    z=PnL,
    hovertemplate=
    "Speed (z): %{x:.2f}%<br>" +
    "Rank: %{y:.3f}<br>" +
    "PnL: %{z:.2f}<extra></extra>"
)])

fig.update_layout(
    title="Max PnL surface (interactive)",
    scene=dict(
        xaxis_title="z (% Speed)",
        yaxis_title="Rank (0→1)",
        zaxis_title="Max PnL"
    )
)

fig.show()



print('-'*10)
print(optimal_pnl_given_z_rank(41,0.1))
print(optimal_pnl_given_z_rank(41,0.15))
print(optimal_pnl_given_z_rank(41,0.2))
print(optimal_pnl_given_z_rank(41,0.3))
print(optimal_pnl_given_z_rank(41,0.4))

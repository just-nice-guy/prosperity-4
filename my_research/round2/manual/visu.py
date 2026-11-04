import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize_scalar

BUDGET = 50_000

# =========================
# Fonctions du modèle
# =========================

def research(x):
    return 200_000 * np.log(1 + x) / np.log(101)

def scale(y):
    return 7 * y / 100

def speed_multiplier(rank):
    return 0.1 + 0.8 * rank  # rank ∈ [0,1]

def pnl(x, y, speed):
    return research(x) * scale(y) * speed - BUDGET

# =========================
# Optimisation pour (z, rank)
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
        method="bounded",
        options={"xatol": 1e-6}
    )

    x_opt = res.x
    y_opt = 100 - z - x_opt
    pnl_opt = pnl(x_opt, y_opt, v)

    return pnl_opt

# =========================
# Grille
# =========================

z_vals = np.linspace(0, 100, 60)
rank_vals = np.linspace(0, 1, 60)

Z, R = np.meshgrid(z_vals, rank_vals)
PnL = np.zeros_like(Z)

# Calcul
for i in range(Z.shape[0]):
    for j in range(Z.shape[1]):
        z = Z[i, j]
        r = R[i, j]
        PnL[i, j] = optimal_pnl_given_z_rank(z, r)

# =========================
# Plot 3D
# =========================

fig = plt.figure(figsize=(10, 7))
ax = fig.add_subplot(111, projection='3d')

ax.plot_surface(Z, R, PnL)

ax.set_xlabel("z (% Speed)")
ax.set_ylabel("Rank (0 = worst, 1 = best)")
ax.set_zlabel("Max PnL")

plt.title("Max PnL as function of Speed allocation and Rank")

plt.show()

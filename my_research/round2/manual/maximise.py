import numpy as np
from scipy.optimize import minimize_scalar

BUDGET = 50_000

def research(x):
    return 200_000 * np.log(1 + x) / np.log(101)

def scale(y):
    return 7 * y / 100

def pnl_full_budget(x, y, speed_multiplier):
    # Ici on impose toujours budget total utilisé
    return research(x) * scale(y) * speed_multiplier - BUDGET

# =========================================================
# 1) MAX PnL avec z = 0, speed = 0.1, budget total utilisé
#    Donc y = 100 - x
# =========================================================

def solve_no_speed():
    def objective(x):
        y = 100 - x
        return -pnl_full_budget(x, y, 0.1)

    res = minimize_scalar(
        objective,
        bounds=(0.0, 100.0),
        method="bounded",
        options={"xatol": 1e-15}
    )

    x_opt = res.x
    y_opt = 100 - x_opt
    z_opt = 0.0
    pnl_opt = pnl_full_budget(x_opt, y_opt, 0.1)

    return x_opt, y_opt, z_opt, pnl_opt

# =========================================================
# 2) Maximiser z avec speed = 0.9 et même PnL
#    Comme x + y + z = 100, maximiser z revient à minimiser x+y
#
#    Contrainte de PnL :
#      research(x) * scale(y) * 0.9 - 50000 = target_pnl
#
#    soit :
#      research(x) * scale(y) = (target_pnl + 50000) / 0.9
#
#    Donc pour un x donné :
#      y = target_gross / (0.9? non)
#
#    Attention :
#      scale(y)=7*y/100
#      research(x) * (7*y/100) = target_gross
#      y = target_gross * 100 / (7 * research(x))
# =========================================================

def solve_max_z_same_pnl(target_pnl):
    target_gross = (target_pnl + BUDGET) / 0.9

    def sum_xy(x):
        rx = research(x)
        if rx <= 0:
            return np.inf
        y = target_gross * 100 / (7 * rx)
        return x + y

    res = minimize_scalar(
        sum_xy,
        bounds=(1e-15, 100.0),
        method="bounded",
        options={"xatol": 1e-15}
    )

    x_opt = res.x
    y_opt = target_gross * 100 / (7 * research(x_opt))
    z_opt = 100 - x_opt - y_opt
    pnl_opt = pnl_full_budget(x_opt, y_opt, 0.9)

    return x_opt, y_opt, z_opt, pnl_opt

# =========================================================
# EXECUTION
# =========================================================

x0, y0, z0, pnl0 = solve_no_speed()

print("=== Optimum avec z = 0 et speed = 0.1 ===")
print(f"x = {x0:.15f}")
print(f"y = {y0:.15f}")
print(f"z = {z0:.15f}")
print(f"PnL = {pnl0:.15f}")

x1, y1, z1, pnl1 = solve_max_z_same_pnl(pnl0)

print("\n=== Même PnL avec speed = 0.9 et z maximal ===")
print(f"x = {x1:.15f}")
print(f"y = {y1:.15f}")
print(f"z = {z1:.15f}")
print(f"PnL = {pnl1:.15f}")

print("\n=== Vérification ===")
print(f"Différence de PnL = {pnl1 - pnl0:.15e}")
print(f"x + y + z = {x1 + y1 + z1:.15f}")

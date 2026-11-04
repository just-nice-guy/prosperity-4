import math
import pandas as pd
from matplotlib import pyplot as plt
import numpy as np

path = "../../../Stage2/initial data"
round = 4

products = [
    "HYDROGEL_PACK",
    "VELVETFRUIT_EXTRACT",
    "VEV_4000",
    "VEV_4500",
    "VEV_5000",
    "VEV_5500",
    "VEV_6000",
    "VEV_6500",
]

# --- Chargement des données ---
prices_2 = pd.read_csv(f"{path}/prices_round_{round}_day_1.csv", delimiter=";")
trades_2 = pd.read_csv(f"{path}/trades_round_{round}_day_1.csv", delimiter=";")

prices_1 = pd.read_csv(f"{path}/prices_round_{round}_day_2.csv", delimiter=";")
trades_1 = pd.read_csv(f"{path}/trades_round_{round}_day_2.csv", delimiter=";")
prices_1["timestamp"] += prices_2["timestamp"].max() + 100
trades_1["timestamp"] += prices_2["timestamp"].max() + 100

prices_0 = pd.read_csv(f"{path}/prices_round_{round}_day_3.csv", delimiter=";")
trades_0 = pd.read_csv(f"{path}/trades_round_{round}_day_3.csv", delimiter=";")
prices_0["timestamp"] += prices_1["timestamp"].max() + 100
trades_0["timestamp"] += prices_1["timestamp"].max() + 100

prices = pd.concat([prices_2, prices_1, prices_0], ignore_index=True)
trades = pd.concat([trades_2, trades_1, trades_0], ignore_index=True)

prices.loc[prices["mid_price"] == 0.0, "mid_price"] = np.nan

# --- Mapping global trader -> couleur lisible sur fond blanc ---
all_traders = pd.unique(
    pd.concat([trades["buyer"], trades["seller"]], ignore_index=True).dropna()
)

all_traders = sorted(all_traders)

base_cmaps = ["tab20", "tab20b", "tab20c"]

colors = []
for cmap_name in base_cmaps:
    cmap = plt.get_cmap(cmap_name)
    colors.extend([cmap(i) for i in range(cmap.N)])

color_map = {
    trader: colors[i % len(colors)]
    for i, trader in enumerate(all_traders)
}


def compute_equity_curves(merged):
    df = merged.copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    df["mid_price"] = df["mid_price"].ffill()

    traders = pd.unique(
        pd.concat([df["buyer"], df["seller"]], ignore_index=True).dropna()
    )

    equity_curves = {}

    for trader in traders:
        cash = 0.0
        inventory = 0.0
        equity = []

        for _, row in df.iterrows():
            price = row["price"]
            qty = row["quantity"]
            mid = row["mid_price"]

            if pd.notna(price) and pd.notna(qty):
                if row["buyer"] == trader:
                    cash -= price * qty
                    inventory += qty

                if row["seller"] == trader:
                    cash += price * qty
                    inventory -= qty

            equity.append(cash + inventory * mid)

        equity_curves[trader] = equity

    equity_df = pd.DataFrame(equity_curves)
    equity_df.insert(0, "timestamp", df["timestamp"])
    equity_df.insert(1, "mid_price", df["mid_price"])

    return equity_df


# --- Subplots ---
n_products = len(products)
n_cols = 2
n_rows = math.ceil(n_products / n_cols)

fig, axes = plt.subplots(
    n_rows,
    n_cols,
    figsize=(18, 4.5 * n_rows),
    sharex=True,
    facecolor="white"
)

axes = axes.flatten()

for ax, product in zip(axes, products):
    ax.set_facecolor("white")

    product_prices = prices[prices["product"] == product].copy()
    product_trades = trades[trades["symbol"] == product].copy()

    merged = pd.merge(
        product_prices,
        product_trades,
        on="timestamp",
        how="outer"
    )

    if merged.empty:
        ax.set_title(f"{product} — no data")
        ax.axis("off")
        continue

    equity_df = compute_equity_curves(merged)
    plot_df = equity_df.set_index("timestamp").drop(columns=["mid_price"])

    if plot_df.empty:
        ax.set_title(f"{product} — no traders")
        ax.axhline(0, linestyle="--", linewidth=1)
        continue

    for trader in plot_df.columns:
        ax.plot(
            plot_df.index,
            plot_df[trader],
            label=trader,
            color=color_map.get(trader, "black"),
            linewidth=1.8,
            alpha=0.95
        )

    ax.axhline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)

    ax.set_title(product)
    ax.set_ylabel("Equity")
    ax.set_xlabel("Timestamp")
    ax.legend(fontsize=7, loc="best", frameon=True)

for ax in axes[len(products):]:
    ax.axis("off")

fig.suptitle("Equity curves par trader et par actif", fontsize=16)

plt.tight_layout()
plt.show()

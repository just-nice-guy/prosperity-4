import pandas as pd
from matplotlib import pyplot as plt
import numpy as np

PRODUCT="HYDROGEL_PACK" #"VEV_6500" #"VEV_4000" #"VELVETFRUIT_EXTRACT" #"HYDROGEL_PACK"
path="../../../Stage2/initial data"
round=4

prices_2=pd.read_csv(f'{path}/prices_round_{round}_day_1.csv',delimiter=";")
trades_2=pd.read_csv(f'{path}/trades_round_{round}_day_1.csv',delimiter=";")

prices_1=pd.read_csv(f'{path}/prices_round_{round}_day_2.csv',delimiter=";")
trades_1=pd.read_csv(f'{path}/trades_round_{round}_day_2.csv',delimiter=";")
prices_1['timestamp']+=prices_2['timestamp'].max()+100
trades_1['timestamp']+=prices_2['timestamp'].max()+100

prices_0=pd.read_csv(f'{path}/prices_round_{round}_day_3.csv',delimiter=";")
trades_0=pd.read_csv(f'{path}/trades_round_{round}_day_3.csv',delimiter=";")
prices_0['timestamp']+=prices_1['timestamp'].max()+100
trades_0['timestamp']+=prices_1['timestamp'].max()+100


prices=pd.concat([prices_2, prices_1, prices_0])
trades=pd.concat([trades_2, trades_1, trades_0])

prices[prices['mid_price']==0.0]=np.nan

prices=prices[prices['product']==PRODUCT]
trades=trades[trades['symbol']==PRODUCT]

merged = pd.merge(prices, trades, on="timestamp", how="outer")

def compute_equity_curves(merged):
    df = merged.copy()
    
    # Sécurité : tri chronologique
    #df = df.sort_values(["day", "timestamp"]).reset_index(drop=True)
    
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

            if row["buyer"] == trader:
                cash -= price * qty
                inventory += qty

            if row["seller"] == trader:
                cash += price * qty
                inventory -= qty

            # Mark-to-market
            equity.append(cash + inventory * mid)

        equity_curves[trader] = equity

    equity_df = pd.DataFrame(equity_curves, index=df.index)
    equity_df.insert(0, "day", df["day"])
    equity_df.insert(1, "timestamp", df["timestamp"])
    equity_df.insert(2, "mid_price", df["mid_price"])

    return equity_df

equity_df = compute_equity_curves(merged)

equity_df.set_index("timestamp").drop(columns=["day", "mid_price"]).plot(figsize=(12, 6))
plt.axhline(0, linestyle="--", linewidth=1)
plt.title("Equity curve par trader")
plt.ylabel("Equity")
plt.xlabel("Timestamp")
plt.show()

"""
for i in merged['buyer'].unique().dropna():
    avg_buy=np.sum(merged[(merged['buyer'] == i)]['price']*merged[(merged['buyer'] == i)]['quantity'])/np.sum(merged[(merged['buyer'] == i)]['quantity'])
    avg_sell=np.sum(merged[(merged['seller'] == i)]['price']*merged[(merged['seller'] == i)]['quantity'])/np.sum(merged[(merged['seller'] == i)]['quantity'])
    print(f"{i}: {avg_sell-avg_buy}")

remove = ['buyer','seller','currency','symbol','product','profit_and_loss','day']
#remove = ['buyer','seller','currency','profit_and_loss','day']

for i in remove:
    del merged[i]
"""

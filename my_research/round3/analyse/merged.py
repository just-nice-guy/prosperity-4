import pandas as pd
from matplotlib import pyplot as plt
import numpy as np

PRODUCT="HYDROGEL_PACK"
path="../../../Stage2/initial data"
round=3

prices_2=pd.read_csv(f'{path}/prices_round_{round}_day_0.csv',delimiter=";")
trades_2=pd.read_csv(f'{path}/trades_round_{round}_day_0.csv',delimiter=";")

prices_1=pd.read_csv(f'{path}/prices_round_{round}_day_1.csv',delimiter=";")
trades_1=pd.read_csv(f'{path}/trades_round_{round}_day_1.csv',delimiter=";")
prices_1['timestamp']+=prices_2['timestamp'].max()+100
trades_1['timestamp']+=prices_2['timestamp'].max()+100

prices_0=pd.read_csv(f'{path}/prices_round_{round}_day_2.csv',delimiter=";")
trades_0=pd.read_csv(f'{path}/trades_round_{round}_day_2.csv',delimiter=";")
prices_0['timestamp']+=prices_1['timestamp'].max()+100
trades_0['timestamp']+=prices_1['timestamp'].max()+100


prices=pd.concat([prices_2, prices_1, prices_0])
trades=pd.concat([trades_2, trades_1, trades_0])

prices[prices['mid_price']==0.0]=np.nan

prices=prices[prices['product']==PRODUCT]
trades=trades[trades['symbol']==PRODUCT]

merged = pd.merge(prices, trades, on="timestamp", how="outer")

remove = ['buyer','seller','currency','symbol','product','profit_and_loss','day']
#remove = ['buyer','seller','currency','profit_and_loss','day']

for i in remove:
    del merged[i]
